import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "acceptance"))

from p1_helpers import count, make_legacy_db  # noqa: E402

from hireember.database import close_connection, init_db  # noqa: E402
from hireember.migration import map_apply_status, migrate_database, migrate_tickets  # noqa: E402


def test_map_apply_status():
    assert map_apply_status("failed", None) == ("blocked for human", "")
    assert map_apply_status("failed", "boom") == ("blocked for human", "boom")
    assert map_apply_status(None, None) == ("pending", "")
    assert map_apply_status("weird", None) == ("blocked for human", "unknown status: weird")


@pytest.mark.parametrize("name", ["applypilot.db", "hireember.db"])
def test_interrupted_migration_converges(tmp_path, name):
    db = tmp_path / name
    make_legacy_db(db)
    try:
        migrate_database(db)
        conn = init_db(db)
        total = count(conn, "tickets")
        conn.execute("DELETE FROM ticket_events WHERE ticket_id % 2 = 0")
        conn.execute("DELETE FROM tickets WHERE id % 2 = 0")
        conn.commit()
        remaining = count(conn, "tickets")
        assert migrate_tickets(conn) == total - remaining
        assert count(conn, "tickets") == total
        assert count(conn, "ticket_events") == total
        assert migrate_tickets(conn) == 0
    finally:
        close_connection(db)


def test_unknown_status_and_empty_failed_error(tmp_path):
    db = tmp_path / "hireember.db"
    make_legacy_db(db)
    raw = sqlite3.connect(str(db))
    raw.execute("UPDATE jobs SET apply_status='mystery' WHERE url LIKE '%/manual'")
    raw.execute("UPDATE jobs SET apply_error=NULL WHERE url LIKE '%/failed'")
    raw.commit()
    raw.close()
    try:
        conn = init_db(db)
        rows = dict(conn.execute(
            "SELECT job_url, status_reason FROM tickets WHERE status='blocked for human'"
        ).fetchall())
        assert rows["https://jobs.example/manual"] == "unknown status: mystery"
        assert rows["https://jobs.example/failed"] == ""
    finally:
        close_connection(db)
