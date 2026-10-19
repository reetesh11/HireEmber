import sqlite3

import pytest

from hireember.database import close_connection, init_db
from hireember.migration import create_schema, ensure_phase3_schema


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def test_new_columns_and_table_exist(conn):
    assert "manual_only" in _cols(conn, "companies")
    for col in ("not_before", "submitted_at", "confirmation_link", "session_link", "resume_link"):
        assert col in _cols(conn, "tickets")
    assert _cols(conn, "attempt_log") == [
        "id", "ticket_id", "attempt", "time", "kind", "field", "source", "detail"]


def test_rerunning_adds_columns_once(conn):
    before = _cols(conn, "tickets")
    create_schema(conn)
    ensure_phase3_schema(conn)
    assert _cols(conn, "tickets") == before


def test_old_database_keeps_its_rows(tmp_path):
    raw = sqlite3.connect(str(tmp_path / "old.db"))
    raw.execute("CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    raw.execute("CREATE TABLE tickets (id INTEGER PRIMARY KEY, job_url TEXT, status TEXT)")
    raw.execute("INSERT INTO companies (name) VALUES ('Acme')")
    raw.execute("INSERT INTO tickets (job_url, status) VALUES ('u', 'pending')")
    ensure_phase3_schema(raw)
    assert raw.execute("SELECT name FROM companies").fetchone()[0] == "Acme"
    row = raw.execute("SELECT status, not_before FROM tickets").fetchone()
    assert tuple(row) == ("pending", None)
    raw.close()
