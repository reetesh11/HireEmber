"""AC-1: migrating an ApplyPilot database creates tables, tickets, events and a backup."""

import sqlite3

import pytest

from hireember.database import close_connection, init_db

from p1_helpers import LEGACY_ROWS, UNTOUCHED_URL, count, make_legacy_db, table_names, url_for

NEW_TABLES = {"companies", "tickets", "ticket_events", "queue_items", "answers",
              "resumes", "runs", "settings"}

EXPECTED = {
    "empty": ("pending", ""),
    "tailored": ("pending", ""),
    "in_progress": ("pending", "stale lock from an interrupted run"),
    "applied": ("applied", "unverified"),
    "failed": ("blocked for human", "Timeout on submit button"),
    "manual": ("blocked for human", "manual ATS"),
    "captcha": ("blocked for human", "CAPTCHA"),
    "login_issue": ("blocked for human", "account needed"),
    "expired": ("closed", "role expired"),
}


@pytest.fixture
def migrated(tmp_path):
    from hireember.migration import migrate_database

    db = tmp_path / "applypilot.db"
    make_legacy_db(db)
    backup = migrate_database(db)
    conn = init_db(db)
    yield db, backup, conn
    close_connection(db)


def test_all_tables_created_and_jobs_kept(migrated):
    _, _, conn = migrated
    names = set(table_names(conn))
    assert NEW_TABLES <= names
    assert "jobs" in names
    assert count(conn, "jobs") == len(LEGACY_ROWS) + 1
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert {"company_id", "title_normalized", "location_normalized", "last_seen_at"} <= cols


def test_tickets_status_and_first_event_reason_per_old_status(migrated):
    _, _, conn = migrated
    from hireember.tickets import get_history, get_ticket_by_url

    assert count(conn, "tickets") == len(LEGACY_ROWS)
    for name, (status, reason) in EXPECTED.items():
        ticket = get_ticket_by_url(conn, url_for(name))
        assert ticket is not None, name
        assert ticket["status"] == status, name
        history = get_history(conn, ticket["id"])
        assert len(history) == 1, name
        assert history[0]["actor"] == "system", name
        assert history[0]["status"] == status, name
        assert (history[0]["reason"] or "") == reason, name
        assert bool(ticket["unverified"]) is (name == "applied"), name
    assert get_ticket_by_url(conn, UNTOUCHED_URL) is None


def test_normalized_columns_filled_for_existing_rows(migrated):
    _, _, conn = migrated
    row = conn.execute(
        "SELECT title_normalized, location_normalized FROM jobs WHERE url=?",
        (url_for("empty"),),
    ).fetchone()
    assert row["title_normalized"] == "senior engineer remote"
    assert row["location_normalized"] == "new york ny"
    assert conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE title_normalized IS NULL OR location_normalized IS NULL"
    ).fetchone()[0] == 0


def test_backup_file_next_to_db_with_original_rows(migrated):
    db, backup, _ = migrated
    found = list(db.parent.glob(db.name + ".bak-*"))
    assert len(found) == 1
    assert backup is not None and backup.resolve() == found[0].resolve()
    old = sqlite3.connect(str(found[0]))
    try:
        assert old.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == len(LEGACY_ROWS) + 1
    finally:
        old.close()


def test_fresh_install_makes_no_backup(tmp_path):
    from hireember.migration import migrate_database

    db = tmp_path / "hireember.db"
    try:
        assert migrate_database(db) is None
        assert list(tmp_path.glob("*.bak-*")) == []
        conn = init_db(db)
        assert NEW_TABLES <= set(table_names(conn))
        assert count(conn, "tickets") == 0
    finally:
        close_connection(db)


def test_store_jobs_fills_normalized_columns_and_last_seen(tmp_path):
    from hireember.database import store_jobs

    db = tmp_path / "hireember.db"
    try:
        conn = init_db(db)
        store_jobs(conn, [{"url": "https://x.example/1", "title": "Staff  Dev!", "location": "Remote, US"}],
                   "S", "t")
        row = conn.execute("SELECT * FROM jobs").fetchone()
        assert row["title_normalized"] == "staff dev"
        assert row["location_normalized"] == "remote us"
        assert row["last_seen_at"]
    finally:
        close_connection(db)
