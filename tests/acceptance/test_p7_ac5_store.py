"""Phase 7 AC-5: chunks live in SQLite (resume_chunks + FTS5), offline, no embedding backend."""

import re
import socket

import pytest

from p7_helpers import text_file


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_migration_creates_chunk_table_and_fts5_index(conn):
    names = {r[0]: (r[1] or "") for r in conn.execute("SELECT name, sql FROM sqlite_master")}
    assert "resume_chunks" in names
    fts = [n for n, sql in names.items() if re.search(r"USING\s+fts5", sql, re.IGNORECASE)]
    assert fts, "no FTS5 virtual table found"


def test_init_db_twice_keeps_chunks(isolated_db, tmp_path):
    from hireember import config
    from hireember.database import init_db
    from hireember.resumes import add_resume

    c = init_db()
    config.ensure_dirs()
    rid = add_resume(c, text_file(tmp_path, "Skills\nPython"), "Keep one")
    c2 = init_db()
    assert c2.execute("SELECT COUNT(*) FROM resume_chunks WHERE resume_id = ?", (rid,)).fetchone()[0] >= 1


def test_add_and_search_work_with_network_disabled(conn, tmp_path, monkeypatch):
    from hireember.resumes import add_resume, search

    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    rid = add_resume(conn, text_file(tmp_path, "Skills\nPython and Rust"), "Offline one")
    assert [h["resume_id"] for h in search(conn, "Rust")] == [rid]
