"""Base resumes (implementation tests)."""

import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.resumes import (ResumeError, add_resume, choose_resume, get_resume_text, list_resumes,
                               pin_resume, unpin_resume, update_resume)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    config.ensure_dirs()
    yield c
    close_connection(db)


def _file(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_add_list_pin_unpin(conn, tmp_path):
    a = add_resume(conn, _file(tmp_path, "a.txt", "A"), "A", " Back , PYTHON,back")
    assert list_resumes(conn)[0]["tags"] == ["back", "python"]
    pin_resume(conn, a)
    assert list_resumes(conn)[0]["pinned"] is True
    unpin_resume(conn)
    assert list_resumes(conn)[0]["pinned"] is False


def test_errors(conn, tmp_path):
    add_resume(conn, _file(tmp_path, "a.txt", "A"), "A")
    with pytest.raises(ResumeError, match="already exists"):
        add_resume(conn, _file(tmp_path, "b.txt", "B"), "a")
    with pytest.raises(ResumeError, match="Unsupported format"):
        add_resume(conn, _file(tmp_path, "b.doc", "B"), "B")
    with pytest.raises(ResumeError, match="No resume with id 9"):
        pin_resume(conn, 9)


def test_pdf_text_copy_and_update(conn, tmp_path):
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    rid = add_resume(conn, pdf, "C", text_file=_file(tmp_path, "c.txt", "TEXT"))
    assert get_resume_text(conn, rid) == "TEXT"
    update_resume(conn, rid, _file(tmp_path, "d.txt", "NEW"))
    assert get_resume_text(conn, rid) == "NEW"


def test_best_fit_ties_and_pin(conn, tmp_path):
    assert choose_resume(conn, {"title": "x"}) is None
    a = add_resume(conn, _file(tmp_path, "a.txt", "A"), "A", "frontend")
    b = add_resume(conn, _file(tmp_path, "b.txt", "B"), "B", "backend")
    c = add_resume(conn, _file(tmp_path, "c.txt", "C"), "C", "backend")
    assert choose_resume(conn, {"title": "Backend Dev"}) == b
    assert choose_resume(conn, {"title": "Chef"}) == a
    pin_resume(conn, c)
    assert choose_resume(conn, {"title": "Backend Dev"}) == c
