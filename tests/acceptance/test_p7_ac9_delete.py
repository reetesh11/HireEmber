"""Phase 7 AC-9: deleting a resume removes file, text copy and chunks; ticket-used resumes are protected."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from p4_helpers import make_ticket
from p7_helpers import Client, base_dir, docx_bytes, post_raw, start_server, stop_server, text_file


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


def _fts_hits(conn, term):
    from hireember.resumes import search

    return search(conn, term)


def test_delete_txt_removes_file_and_chunks(env, tmp_path):
    from hireember.resumes import add_resume, delete_resume, list_resumes

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path, "Skills\nZirconium"), "Del txt")
    stored = Path(_row(conn, rid)["file_path"])
    assert stored.is_file() and _fts_hits(conn, "Zirconium")
    delete_resume(conn, rid)
    assert not stored.exists()
    assert rid not in [r["id"] for r in list_resumes(conn)]
    assert conn.execute("SELECT COUNT(*) FROM resume_chunks WHERE resume_id = ?", (rid,)).fetchone()[0] == 0
    assert _fts_hits(conn, "Zirconium") == []


def test_delete_docx_removes_text_copy_too(env, tmp_path):
    from hireember.resumes import add_resume, delete_resume

    conn, _ = env
    src = tmp_path / "cv.docx"
    src.write_bytes(docx_bytes(["Skills", "Ytterbium"]))
    rid = add_resume(conn, src, "Del docx")
    stored = Path(_row(conn, rid)["file_path"])
    siblings = [p for p in stored.parent.iterdir() if p.name.startswith(stored.stem)]
    assert len(siblings) >= 2
    delete_resume(conn, rid)
    assert [p for p in stored.parent.iterdir() if p in siblings] == []
    assert _fts_hits(conn, "Ytterbium") == []


def test_delete_pdf_removes_text_copy(env, tmp_path):
    from hireember.resumes import add_resume, delete_resume

    conn, _ = env
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    rid = add_resume(conn, pdf, "Del pdf", text_file=text_file(tmp_path, "Skills\nNeodymium"))
    stored = Path(_row(conn, rid)["file_path"])
    assert stored.with_suffix(".txt").is_file()
    delete_resume(conn, rid)
    assert not stored.exists() and not stored.with_suffix(".txt").exists()
    assert _fts_hits(conn, "Neodymium") == []


def test_other_resumes_keep_their_chunks(env, tmp_path):
    from hireember.resumes import add_resume, delete_resume

    conn, _ = env
    a = add_resume(conn, text_file(tmp_path, "Skills\nOsmium shared"), "Keep a")
    b = add_resume(conn, text_file(tmp_path, "Skills\nOsmium shared"), "Drop b")
    delete_resume(conn, b)
    assert [h["resume_id"] for h in _fts_hits(conn, "Osmium")] == [a]


def test_delete_blocked_when_a_ticket_uses_the_resume(env, tmp_path):
    from hireember.resumes import ResumeError, add_resume, delete_resume
    from hireember.tickets import set_ticket_resume

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path, "Skills\nIridium"), "Used one")
    stored = Path(_row(conn, rid)["file_path"])
    t1 = make_ticket(conn, "del1")
    t2 = make_ticket(conn, "del2")
    set_ticket_resume(conn, t1, rid)
    set_ticket_resume(conn, t2, rid)
    with pytest.raises(ResumeError) as exc:
        delete_resume(conn, rid)
    assert str(exc.value) == 'Resume "Used one" is used by 2 ticket(s) and cannot be deleted.'
    assert stored.is_file() and _fts_hits(conn, "Iridium")
    assert _row(conn, rid)["chunk_count"] >= 1


def test_delete_unknown_id(env):
    from hireember.resumes import ResumeError, delete_resume

    conn, _ = env
    with pytest.raises(ResumeError) as exc:
        delete_resume(conn, 9999)
    assert str(exc.value) == "No resume with id 9999."


def test_api_delete(env):
    conn, client = env
    status, created = post_raw(client, "a.txt", b"Skills\nRhodium", "Api del")
    assert status == 201
    status, body = client.json("DELETE", f"/api/resumes/{created['id']}")
    assert status == 200 and body == {"ok": True}
    assert not (base_dir() / created["file_name"]).exists()
    status, listing = client.get("/api/resumes")
    assert created["id"] not in [r["id"] for r in listing["resumes"]]
    assert client.json("DELETE", f"/api/resumes/{created['id']}")[0] == 404


def test_api_delete_blocked_by_ticket(env):
    from hireember.tickets import set_ticket_resume

    conn, client = env
    status, created = post_raw(client, "a.txt", b"Skills\nPalladium", "Api used")
    set_ticket_resume(conn, make_ticket(conn, "del3"), created["id"])
    status, body = client.json("DELETE", f"/api/resumes/{created['id']}")
    assert status == 400
    assert body["error"] == 'Resume "Api used" is used by 1 ticket(s) and cannot be deleted.'
    assert created["id"] in [r["id"] for r in client.get("/api/resumes")[1]["resumes"]]


def test_cli_delete(env, tmp_path):
    from hireember.cli import app
    from hireember.resumes import add_resume

    conn, _ = env
    rid = add_resume(conn, text_file(tmp_path), "Cli del")
    res = CliRunner().invoke(app, ["resume", "delete", str(rid)])
    assert res.exit_code == 0, res.output
    assert f"Deleted resume {rid}." in res.output
    again = CliRunner().invoke(app, ["resume", "delete", str(rid)])
    assert again.exit_code == 1 and f"No resume with id {rid}." in again.output
    assert re.search(r"Delete", CliRunner().invoke(app, ["resume", "--help"]).output)


def test_dashboard_has_delete_with_confirm(env):
    _, client = env
    page = client.request("GET", "/")[2].decode("utf-8")
    assert '"Delete"' in page or ">Delete<" in page
    assert "Resume deleted." in page
    assert "confirm(" in page
