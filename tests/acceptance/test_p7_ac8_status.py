"""Phase 7 AC-8: extraction status and chunk count per resume, re-extract, replace re-runs extraction."""

import uuid
from pathlib import Path

import pytest
from typer.testing import CliRunner

from p2_helpers import widen_cli_console
from p7_helpers import (Client, base_dir, blank_pdf_bytes, post_raw, start_server, stop_server, text_file)

SCANNED = "this looks like a scanned PDF. OCR is not supported. Add a text copy or a text-based PDF."


@pytest.fixture
def env(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    conn = init_db()
    config.ensure_dirs()
    server, thread = start_server(isolated_db)
    yield conn, Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


def _row(conn, rid):
    from hireember.resumes import list_resumes

    return [r for r in list_resumes(conn) if r["id"] == rid][0]


def _legacy(conn, name="Legacy"):
    path = base_dir() / f"legacy_{uuid.uuid4().hex[:6]}.txt"
    path.write_text("Experience\nBuilt Python APIs.", encoding="utf-8")
    cur = conn.execute("INSERT INTO resumes (name, tags, file_path, pinned, added_at) VALUES (?, '', ?, 0, 'now')",
                       (name, str(path)))
    conn.commit()
    return cur.lastrowid


# -- Python API --------------------------------------------------------------

def test_legacy_row_is_not_extracted_with_zero_chunks(env):
    conn, _ = env
    row = _row(conn, _legacy(conn))
    assert (row["extract_status"], row["extract_reason"], row["chunk_count"]) == ("not_extracted", "", 0)


def test_extract_resume_on_legacy_row_extracts(env):
    from hireember.resumes import extract_resume

    conn, _ = env
    rid = _legacy(conn)
    result = extract_resume(conn, rid)
    assert result.status == "extracted" and result.chunks >= 1 and result.reason == ""
    row = _row(conn, rid)
    assert row["extract_status"] == "extracted" and row["chunk_count"] == result.chunks


def test_corrupt_docx_is_failed_with_reason(env, tmp_path):
    from hireember.resumes import add_resume

    conn, _ = env
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"not a zip")
    rid = add_resume(conn, bad, "Bad docx")
    row = _row(conn, rid)
    assert row["extract_status"] == "failed"
    assert row["extract_reason"] == "this .docx file could not be read."
    assert row["chunk_count"] == 0


def test_scanned_pdf_is_no_text_with_reason(env, tmp_path):
    from hireember.resumes import add_resume

    conn, _ = env
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(blank_pdf_bytes())
    rid = add_resume(conn, pdf, "Scanned")
    row = _row(conn, rid)
    assert (row["extract_status"], row["extract_reason"], row["chunk_count"]) == ("no_text", SCANNED, 0)


def test_whitespace_txt_is_no_text(env, tmp_path):
    from hireember.resumes import add_resume

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path, "   \n\n  \t "), "Blank text")
    row = _row(conn, rid)
    assert (row["extract_status"], row["extract_reason"], row["chunk_count"]) == (
        "no_text", "the file has no text.", 0)


def test_missing_stored_file_is_failed(env, tmp_path):
    from hireember.resumes import add_resume, extract_resume

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path), "Vanishing")
    Path(_row(conn, rid)["file_path"]).unlink()
    result = extract_resume(conn, rid)
    assert result.status == "failed"
    assert result.reason == "The stored file is missing. Replace the file."
    assert _row(conn, rid)["chunk_count"] == 0


def test_extract_unknown_id_raises(env):
    from hireember.resumes import ResumeError, extract_resume

    conn, _ = env
    with pytest.raises(ResumeError) as exc:
        extract_resume(conn, 9999)
    assert str(exc.value) == "No resume with id 9999."


def test_replace_file_reruns_extraction_and_drops_stale_chunks(env, tmp_path):
    from hireember.resumes import add_resume, search, update_resume

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path, "Skills\nCobol"), "Swap")
    blank = tmp_path / "blank.txt"
    blank.write_text("   ")
    update_resume(conn, rid, blank)
    row = _row(conn, rid)
    assert row["extract_status"] == "no_text" and row["chunk_count"] == 0
    assert search(conn, "Cobol") == []


# -- HTTP --------------------------------------------------------------------

def test_api_list_carries_status_fields(env):
    conn, client = env
    rid = _legacy(conn)
    status, body = client.get("/api/resumes")
    assert status == 200
    r = [x for x in body["resumes"] if x["id"] == rid][0]
    assert r["extract_status"] == "not_extracted" and r["extract_reason"] == "" and r["chunk_count"] == 0


def test_api_extract_endpoint_success(env):
    conn, client = env
    rid = _legacy(conn)
    status, body = client.json("POST", f"/api/resumes/{rid}/extract", {})
    assert status == 200
    assert body["ok"] is True
    assert body["message"] == f"Extraction finished: {body['resume']['chunk_count']} chunks."
    assert body["resume"]["extract_status"] == "extracted" and body["resume"]["chunk_count"] >= 1


def test_api_extract_endpoint_failure_message(env):
    conn, client = env
    status, created = post_raw(client, "scan.pdf", blank_pdf_bytes(), "Scan api")
    assert status == 201
    status, body = client.json("POST", f"/api/resumes/{created['id']}/extract")
    assert status == 200
    assert body["ok"] is False
    assert body["message"] == f"Extraction failed: {SCANNED}"
    assert body["resume"]["extract_status"] == "no_text"


def test_api_replace_file_reextracts(env):
    conn, client = env
    status, created = post_raw(client, "a.txt", b"Skills\nCobol", "Replace api")
    assert status == 201
    status, _, payload = client.request(
        "POST", f"/api/resumes/{created['id']}/file",
        headers={"X-Filename": "b.txt", "Content-Type": "application/octet-stream"}, raw=b"Skills\nHaskell")
    import json
    body = json.loads(payload)
    assert status == 200
    assert body["ok"] is True and body["message"] == "Resume file replaced."
    assert body["resume"]["extract_status"] == "extracted"
    from hireember.resumes import search
    assert [h["resume_id"] for h in search(conn, "Haskell")] == [created["id"]]
    assert search(conn, "Cobol") == []


# -- CLI and UI --------------------------------------------------------------

def test_cli_list_shows_extraction_and_chunks(env, monkeypatch, tmp_path):
    from hireember.cli import app
    from hireember.resumes import add_resume

    conn, _ = env
    widen_cli_console(monkeypatch)
    add_resume(conn, text_file(tmp_path), "Listed")
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"junk")
    add_resume(conn, bad, "Listed bad")
    _legacy(conn, "Listed legacy")
    out = CliRunner().invoke(app, ["resume", "list"])
    assert out.exit_code == 0, out.output
    assert "Extraction" in out.output and "Chunks" in out.output
    assert "Extracted" in out.output
    assert "Failed: this .docx file could not be read." in out.output
    assert "Not extracted" in out.output


def test_dashboard_page_has_status_and_reextract_strings(env):
    _, client = env
    status, _, payload = client.request("GET", "/")
    page = payload.decode("utf-8")
    for s in ("Extraction", "Chunks", "Re-extract", "Not extracted", "Failed: ", "No text found: ",
              "Extraction finished: ", "Extraction failed: ", "Resume file replaced."):
        assert s in page, s
    assert 'accept=".pdf,.txt,.docx"' in page
