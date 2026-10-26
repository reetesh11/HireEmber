"""Phase 5 schema additions: run columns, run_lock, run_log."""

import sqlite3

from hireember import migration

RUN_COLUMNS = {"trigger", "status", "found", "scored", "skipped", "tickets_created", "tickets_blocked"}


def _columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_fresh_db_has_phase5_schema(isolated_db):
    from hireember.database import init_db

    conn = init_db()
    assert RUN_COLUMNS <= _columns(conn, "runs")
    assert {"pid", "token", "run_id", "acquired_at"} <= _columns(conn, "run_lock")
    assert {"run_id", "time", "source", "level", "message"} <= _columns(conn, "run_log")


def test_upgrade_old_runs_table_and_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, kind TEXT, started_at TEXT, "
                 "ended_at TEXT, summary TEXT)")
    conn.execute("INSERT INTO runs (kind) VALUES ('old')")
    migration.ensure_phase5_schema(conn)
    migration.ensure_phase5_schema(conn)
    assert RUN_COLUMNS <= _columns(conn, "runs")
    assert conn.execute("SELECT kind FROM runs").fetchone()[0] == "old"
