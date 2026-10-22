"""Resume metadata update (implementation tests)."""

import pytest

from hireember import resumes
from hireember.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def _file(tmp_path, name):
    p = tmp_path / name
    p.write_text("text", encoding="utf-8")
    return p


def test_rename_tags_and_errors(conn, tmp_path):
    a = resumes.add_resume(conn, _file(tmp_path, "a.txt"), "Alpha")
    resumes.add_resume(conn, _file(tmp_path, "b.txt"), "Beta")
    resumes.update_resume_meta(conn, a, name=" Alpha 2 ", tags="Go, go, Rust")
    row = resumes.list_resumes(conn)[0]
    assert row["name"] == "Alpha 2" and row["tags"] == ["go", "rust"]
    with pytest.raises(resumes.ResumeError, match="Name cannot be empty."):
        resumes.update_resume_meta(conn, a, name=" ")
    with pytest.raises(resumes.ResumeError, match="already exists"):
        resumes.update_resume_meta(conn, a, name="BETA")
    with pytest.raises(resumes.ResumeError):
        resumes.update_resume_meta(conn, 99, name="x")
