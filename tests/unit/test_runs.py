"""Run model: lock handling, stale reclaim, blocked tickets, logging."""

import os
from datetime import timedelta

import pytest

from hireember import runs
from hireember.runs import Stages


def _stages(**over):
    base = {n: (lambda conn, run_id, *a: {}) for n in ("discover", "enrich", "score", "tailor", "apply")}
    base.update(over)
    return Stages(**base)


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_dead_pid_lock_is_reclaimed_and_running_row_interrupted(conn, monkeypatch):
    conn.execute("INSERT INTO runs (kind, status, started_at) VALUES ('full', 'running', 'x')")
    conn.execute("INSERT INTO run_lock (id, pid, token, acquired_at) VALUES (1, 999999, 't', ?)",
                 (runs._utcnow().isoformat(),))
    conn.commit()
    monkeypatch.setattr(runs, "is_pid_alive", lambda pid: False)
    summary = runs.execute_run("manual", stages=_stages(), conn=conn)
    assert summary.status == "completed"
    statuses = [r[0] for r in conn.execute("SELECT status FROM runs ORDER BY id")]
    assert statuses == ["interrupted", "completed"]


def test_old_lock_is_stale_even_when_pid_alive(conn):
    old = (runs._utcnow() - runs.LOCK_MAX_AGE - timedelta(minutes=1)).isoformat()
    conn.execute("INSERT INTO run_lock (id, pid, token, acquired_at) VALUES (1, ?, 't', ?)",
                 (os.getpid(), old))
    conn.commit()
    assert runs.execute_run("manual", stages=_stages(), conn=conn).status == "completed"


def test_live_lock_blocks(conn):
    token = runs.acquire_lock(conn)
    with pytest.raises(runs.RunInProgressError):
        runs.acquire_lock(conn)
    assert runs.is_running(conn)
    runs.release_lock(conn, token)
    assert not runs.is_running(conn)


def test_is_pid_alive():
    assert runs.is_pid_alive(os.getpid())
    assert not runs.is_pid_alive(0)


def test_log_event_order(conn):
    runs.log_event(conn, 1, "a", "first")
    runs.log_event(conn, 1, "b", "second", level="info")
    assert [e["message"] for e in runs.get_run_log(conn, 1)] == ["first", "second"]


def test_lock_released_when_interrupted(conn):
    def boom(c, rid):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        runs.execute_run("manual", stages=_stages(discover=boom), conn=conn)
    assert not runs.is_running(conn)
    assert conn.execute("SELECT status FROM runs").fetchone()[0] == "interrupted"


def test_old_runs_rows_without_summary_columns_read_blank(conn):
    conn.execute("INSERT INTO runs (kind, started_at) VALUES ('old', 'x')")
    conn.commit()
    r = runs.list_runs(conn)[0]
    assert (r.trigger, r.status, r.found) == ("", "", 0)
