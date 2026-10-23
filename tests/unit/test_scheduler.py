"""Scheduler details beyond the acceptance flows: time zones, polling loop, quota boundaries."""

import threading
from datetime import datetime, timedelta, timezone

import pytest

from hireember import runs, scheduler


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def _stages():
    return runs.Stages(**{n: (lambda c, rid, *a: {}) for n in
                          ("discover", "enrich", "score", "tailor", "apply")})


def test_due_slot_uses_the_tzinfo_of_now(conn):
    plus2 = timezone(timedelta(hours=2))
    scheduler.set_schedule(conn, ["08:00"], now=datetime(2026, 3, 1, 5, 0, tzinfo=plus2))
    assert scheduler.due_slot(conn, datetime(2026, 3, 1, 7, 59, tzinfo=plus2)) is None
    assert scheduler.due_slot(conn, datetime(2026, 3, 1, 8, 0, tzinfo=plus2)) == \
        datetime(2026, 3, 1, 8, 0, tzinfo=plus2)


def test_slot_consumed_when_run_rejected(conn):
    scheduler.set_schedule(conn, ["08:00"], now=datetime(2026, 3, 1, 7, tzinfo=timezone.utc))
    token = runs.acquire_lock(conn)
    now = datetime(2026, 3, 1, 8, tzinfo=timezone.utc)
    assert scheduler.tick(conn, now, stages=_stages()) is None
    runs.release_lock(conn, token)
    assert scheduler.tick(conn, now + timedelta(minutes=1), stages=_stages()) is None
    assert conn.execute("SELECT COUNT(*) FROM run_log WHERE source = 'scheduler'").fetchone()[0] == 1


def test_serve_stops_on_event(conn):
    stop = threading.Event()
    ticks = []
    stop.set()
    scheduler.serve(poll_seconds=0.01, stop=stop, clock=lambda: ticks.append(1))
    assert ticks == []


def test_set_apply_rejects_bad_limit(conn):
    with pytest.raises(ValueError):
        scheduler.set_apply(conn, limit=-3)
