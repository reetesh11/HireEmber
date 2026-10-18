from datetime import datetime, timedelta, timezone

import pytest

from hireember.apply import limits
from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import get_ticket, set_job_score, set_setting, set_status

NOW = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def add(conn, n, company="Acme", score=8):
    store_jobs(conn, [{"url": f"u{n}", "title": f"T{n}", "company": company,
                       "location": f"L{n}"}], "S", "t")
    return set_job_score(conn, f"u{n}", score)


def test_third_open_passes_fourth_holds(conn):
    for i in range(2):
        set_status(conn, add(conn, i), "started")
    third = add(conn, 2)
    assert limits.check_limits(conn, third, NOW).ok
    set_status(conn, third, "started")
    fourth = add(conn, 3)
    result = limits.check_limits(conn, fourth, NOW)
    assert not result.ok and result.reason == "limit: company (3 open)"


def test_company_wait_after_submission(conn):
    first, second = add(conn, 1), add(conn, 2)
    other = add(conn, 3, company="Other")
    conn.execute("UPDATE tickets SET submitted_at = ? WHERE id = ?", (NOW.isoformat(), first))
    conn.commit()
    result = limits.check_limits(conn, second, NOW + timedelta(hours=1))
    assert not result.ok and result.reason == "limit: company wait until 2026-10-19 10:00"
    assert result.not_before == (NOW + timedelta(hours=24)).isoformat()
    assert limits.check_limits(conn, other, NOW).ok
    assert limits.check_limits(conn, second, NOW + timedelta(hours=25)).ok


def test_daily_limit_and_settings_override(conn):
    set_setting(conn, "max_per_day", "1")
    first, second = add(conn, 1, "A"), add(conn, 2, "B")
    conn.execute("UPDATE tickets SET submitted_at = ? WHERE id = ?", (NOW.isoformat(), first))
    conn.commit()
    result = limits.check_limits(conn, second, NOW)
    assert result.reason == "limit: daily"
    assert result.not_before == "2026-10-19T00:00:00+00:00"
    assert limits.check_limits(conn, second, NOW + timedelta(days=1)).ok


def test_hold_and_record_submission_and_eligible(conn):
    first, second, other = add(conn, 1, score=9), add(conn, 2), add(conn, 3, "Other", 7)
    limits.record_submission(conn, first, NOW)
    held = get_ticket(conn, second)
    assert held["status"] == "pending" and held["status_reason"].startswith("limit: company wait")
    assert limits.eligible_ticket_ids(conn, NOW) == [first, other]
    assert limits.eligible_ticket_ids(conn, NOW + timedelta(hours=25)) == [first, second, other]
    result = limits.LimitResult(False, "limit: daily", "2030-01-01T00:00:00+00:00")
    set_status(conn, other, "started")
    limits.hold_ticket(conn, other, result)
    assert get_ticket(conn, other)["status"] == "pending"
    assert get_ticket(conn, other)["not_before"] == result.not_before
