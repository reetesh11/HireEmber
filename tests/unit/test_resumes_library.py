"""Resume library: formats, extraction status, delete, search (implementation tests)."""

import logging
from pathlib import Path

import pytest
from docx import Document

from hireember import config
from hireember.database import close_connection, init_db
from hireember.resumes import (MAX_UPLOAD_BYTES, ResumeError, add_resume, add_resume_bytes, delete_resume,
                               extract_resume, get_resume_text, list_resumes, search, update_resume)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    config.ensure_dirs()
    yield c
    close_connection(db)


def _txt(tmp_path, text, name="a.txt"):
    p = tmp_path / name
    p.write_bytes(text if isinstance(text, bytes) else text.encode())
    return p


def _row(conn, rid):
    return [r for r in list_resumes(conn) if r["id"] == rid][0]


def _docx(tmp_path, *lines, name="cv.docx"):
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    p = tmp_path / name
    doc.save(str(p))
    return p


def test_add_docx_extracts_and_keeps_text_copy(conn, tmp_path):
    rid = add_resume(conn, _docx(tmp_path, "Skills", "Python and Rust"), "D")
    row = _row(conn, rid)
    assert row["extract_status"] == "extracted" and row["chunk_count"] == 1
    assert "Rust" in get_resume_text(conn, rid)
    assert [h["resume_id"] for h in search(conn, "rust")] == [rid]


def test_non_utf8_txt_and_whitespace_only(conn, tmp_path):
    rid = add_resume(conn, _txt(tmp_path, b"Skills\nPython caf\xe9"), "L")
    assert _row(conn, rid)["extract_status"] == "extracted"
    rid2 = add_resume(conn, _txt(tmp_path, "  \n ", "b.txt"), "B")
    assert _row(conn, rid2)["extract_status"] == "no_text"


def test_corrupt_docx_failed_and_missing_file(conn, tmp_path):
    rid = add_resume(conn, _txt(tmp_path, b"junk", "bad.docx"), "Bad")
    assert _row(conn, rid)["extract_status"] == "failed"
    rid2 = add_resume(conn, _txt(tmp_path, "Skills\nGo"), "Gone")
    Path(_row(conn, rid2)["file_path"]).unlink()
    assert extract_resume(conn, rid2).reason == "The stored file is missing. Replace the file."
    with pytest.raises(ResumeError, match="No resume with id 99"):
        extract_resume(conn, 99)


def test_replace_drops_stale_chunks(conn, tmp_path):
    rid = add_resume(conn, _txt(tmp_path, "Skills\nCobol"), "R")
    update_resume(conn, rid, _txt(tmp_path, "Skills\nHaskell", "c.txt"))
    assert search(conn, "cobol") == [] and search(conn, "haskell")


def test_delete_removes_files_chunks_and_respects_tickets(conn, tmp_path):
    rid = add_resume(conn, _docx(tmp_path, "Skills", "Ytterbium"), "Del")
    stored = Path(_row(conn, rid)["file_path"])
    conn.execute("INSERT INTO tickets (job_url, status, resume_id) VALUES ('u', 'new', ?)", (rid,))
    conn.commit()
    with pytest.raises(ResumeError, match="is used by 1 ticket"):
        delete_resume(conn, rid)
    assert stored.exists()
    conn.execute("DELETE FROM tickets")
    conn.commit()
    delete_resume(conn, rid)
    assert not any(p.name.startswith(stored.stem) for p in stored.parent.iterdir())
    assert search(conn, "ytterbium") == [] and list_resumes(conn) == []
    with pytest.raises(ResumeError, match="No resume with id"):
        delete_resume(conn, rid)


def test_size_limits_and_path_traversal(conn):
    assert add_resume_bytes(conn, "a.txt", b"x" * MAX_UPLOAD_BYTES, "Max")
    with pytest.raises(ResumeError, match="larger than 10 MB"):
        add_resume_bytes(conn, "a.txt", b"x" * (MAX_UPLOAD_BYTES + 1), "Over")
    rid = add_resume_bytes(conn, "../../evil.txt", b"hello", "Trav")
    assert Path(_row(conn, rid)["file_path"]).parent == config.APP_DIR / "base_resumes"


def test_resume_text_not_logged(conn, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    rid = add_resume(conn, _txt(tmp_path, "Skills\nZEBRAQUILL"), "Log")
    extract_resume(conn, rid)
    search(conn, "ZEBRAQUILL")
    assert "ZEBRAQUILL" not in caplog.text
