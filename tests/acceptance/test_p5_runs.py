"""Phase 5 run model: runs rows, single-run lock, single stages, blocked tickets in the queue
(AC-1 counts, AC-2, AC-3 at the run level, AC-8, AC-12)."""

import json
import threading

import pytest

from p5_helpers import Recorder, blocking_stages, make_ticket, run_rows, utc


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_execute_run_writes_one_row_with_counts(conn):
    from hireember.runs import execute_run, get_run, list_runs

    def tailor_hook(c, run_id):
        make_ticket(c, "ok1", status="pending")
        make_ticket(c, "blk1", status="blocked for human", status_reason="Needs login")

    rec = Recorder(found=7, scored=5, skipped=2, created=2, blocked=1, hooks={"tailor": tailor_hook})
    summary = execute_run("manual", stages=rec.stages(), conn=conn)
    assert rec.calls == ["discover", "enrich", "score", "tailor"]
    rows = run_rows(conn)
    assert len(rows) == 1
    assert summary.status == "completed" and summary.trigger == "manual" and summary.kind == "full"
    assert (summary.found, summary.scored, summary.skipped) == (7, 5, 2)
    assert summary.tickets_created == 2 and summary.tickets_blocked == 1
    assert summary.ended_at and summary.started_at
    assert get_run(conn, summary.id) == summary
    assert list_runs(conn) == [summary]


def test_missing_stage_keys_count_as_zero(conn):
    from hireember.runs import execute_run

    rec = Recorder()
    rec.results["discover"] = {}
    rec.results["score"] = {}
    rec.results["tailor"] = {}
    s = execute_run("manual", stages=rec.stages(), conn=conn)
    assert (s.found, s.scored, s.skipped, s.tickets_created, s.tickets_blocked) == (0, 0, 0, 0, 0)


def test_apply_not_called_when_off(conn):
    from hireember.runs import execute_run

    rec = Recorder()
    execute_run("scheduled", stages=rec.stages(), conn=conn)
    assert "apply" not in rec.calls


def test_apply_called_with_limit_when_on(conn):
    from hireember.runs import execute_run

    rec = Recorder()
    execute_run("scheduled", stages=rec.stages(), apply=True, apply_limit=4, conn=conn)
    assert rec.calls[-1] == "apply" and rec.apply_limits == [4]
    rec2 = Recorder()
    execute_run("scheduled", stages=rec2.stages(), apply=True, conn=conn)
    assert rec2.apply_limits == [25]
    rec3 = Recorder()
    execute_run("scheduled", stages=rec3.stages(), apply=True, apply_limit=0, conn=conn)
    assert "apply" not in rec3.calls


def test_failing_stage_is_logged_and_run_continues(conn):
    from hireember.runs import execute_run, get_run_log

    def boom(c, run_id):
        raise RuntimeError("score exploded")

    rec = Recorder(hooks={"score": boom})
    s = execute_run("manual", stages=rec.stages(), conn=conn)
    assert rec.calls == ["discover", "enrich", "score", "tailor"]
    assert s.status == "partial"
    assert len(run_rows(conn)) == 1
    log = get_run_log(conn, s.id)
    assert any(e["source"] == "score" and "score exploded" in e["message"] for e in log)


def test_overlapping_runs_produce_one_row(conn):
    from hireember.runs import RunInProgressError, execute_run

    entered, release = threading.Event(), threading.Event()
    first = blocking_stages(entered, release)
    t = threading.Thread(target=lambda: execute_run("manual", stages=first.stages()), daemon=True)
    t.start()
    try:
        assert entered.wait(10)
        second = Recorder()
        with pytest.raises(RunInProgressError) as exc:
            execute_run("scheduled", stages=second.stages(), conn=conn)
        assert str(exc.value) == "A run is already in progress."
        assert second.calls == []
    finally:
        release.set()
        t.join(15)
    assert len(run_rows(conn)) == 1


def test_lock_released_after_run(conn):
    from hireember.runs import execute_run

    execute_run("manual", stages=Recorder().stages(), conn=conn)
    execute_run("manual", stages=Recorder().stages(), conn=conn)
    assert len(run_rows(conn)) == 2


def test_list_runs_newest_first(conn):
    from hireember.runs import execute_run, list_runs

    a = execute_run("manual", stages=Recorder().stages(), conn=conn, now=utc(2026, 1, 1, 8))
    b = execute_run("manual", stages=Recorder().stages(), conn=conn, now=utc(2026, 1, 2, 8))
    assert [r.id for r in list_runs(conn)] == [b.id, a.id]


# -- AC-8: blocked tickets reach the queue ---------------------------------

def test_blocked_tickets_enter_queue_once(conn):
    from hireember.answers import list_queue
    from hireember.runs import enqueue_blocked, execute_run

    def tailor_hook(c, run_id):
        for i in range(3):
            make_ticket(c, f"blocked{i}", status="blocked for human", company=f"Co{i}",
                        status_reason=f"Needs captcha {i}")
            c.execute("UPDATE jobs SET application_url = ? WHERE url = ?",
                      (f"https://apply.example/{i}", f"https://jobs.example/blocked{i}"))
        c.commit()

    rec = Recorder(blocked=3, created=3, hooks={"tailor": tailor_hook})
    s = execute_run("manual", stages=rec.stages(), conn=conn)
    assert s.tickets_blocked == 3
    items = list_queue(conn)
    assert len(items) == 3
    for item in items:
        assert item["company"] and item["reason"] and item["page_link"]
    assert {i["company"] for i in items} == {"Co0", "Co1", "Co2"}
    assert {i["page_link"] for i in items} == {f"https://apply.example/{i}" for i in range(3)}
    assert enqueue_blocked(conn) == 0
    assert len(list_queue(conn)) == 3


def test_enqueue_blocked_defaults(conn):
    from hireember.answers import list_queue
    from hireember.runs import enqueue_blocked

    make_ticket(conn, "plain", status="blocked for human", status_reason="")
    assert enqueue_blocked(conn) == 1
    item = list_queue(conn)[0]
    assert item["reason"] == "Needs your attention"
    assert item["page_link"] == "https://jobs.example/plain"
    assert item["kind"] == "run blocked"


# -- AC-12: single stages ----------------------------------------------------

@pytest.mark.parametrize("stage,expected_msg", [
    ("discover", "discover: 7 roles found, 2 new."),
    ("score", "score: 5 scored, 3 skipped."),
    ("tailor", "tailor: 4 tickets created, 1 blocked."),
    ("apply", "apply: 6 submitted."),
])
def test_run_stage_runs_only_that_stage(conn, stage, expected_msg):
    from hireember.runs import run_stage

    rec = Recorder()
    rec.results = {
        "discover": {"found": 7, "new": 2}, "enrich": {}, "score": {"scored": 5, "skipped": 3},
        "tailor": {"created": 4, "blocked": 1}, "apply": {"submitted": 6},
    }
    result = run_stage(stage, stages=rec.stages(), conn=conn)
    assert rec.calls == [stage]
    assert result.stage == stage and result.message == expected_msg
    assert run_rows(conn) == []
    stored = conn.execute("SELECT value FROM settings WHERE key = 'last_stage_result'").fetchone()
    assert stored and json.loads(stored[0])


def test_run_stage_apply_default_limit_is_one(conn):
    from hireember.runs import run_stage

    rec = Recorder()
    run_stage("apply", stages=rec.stages(), conn=conn)
    assert rec.apply_limits == [1]
    run_stage("apply", stages=rec.stages(), conn=conn, limit=3)
    assert rec.apply_limits == [1, 3]


def test_run_stage_unknown_stage(conn):
    from hireember.runs import run_stage

    with pytest.raises(ValueError):
        run_stage("enrich", stages=Recorder().stages(), conn=conn)


def test_run_stage_enqueues_blocked_after_tailor(conn):
    from hireember.answers import list_queue
    from hireember.runs import run_stage

    rec = Recorder(hooks={"tailor": lambda c, rid: make_ticket(
        c, "b1", status="blocked for human", status_reason="Captcha")})
    run_stage("tailor", stages=rec.stages(), conn=conn)
    assert len(list_queue(conn)) == 1


def test_run_stage_rejected_while_run_in_progress(conn):
    from hireember.runs import RunInProgressError, execute_run, run_stage

    entered, release = threading.Event(), threading.Event()
    t = threading.Thread(
        target=lambda: execute_run("manual", stages=blocking_stages(entered, release).stages()),
        daemon=True)
    t.start()
    try:
        assert entered.wait(10)
        rec = Recorder()
        with pytest.raises(RunInProgressError):
            run_stage("score", stages=rec.stages(), conn=conn)
        assert rec.calls == []
    finally:
        release.set()
        t.join(15)


def test_start_stage_async_holds_lock_then_releases(conn):
    from hireember.runs import RunInProgressError, run_stage, start_stage_async

    entered, release = threading.Event(), threading.Event()
    rec = Recorder(hooks={"score": lambda c, rid: (entered.set(), release.wait(15))})
    thread = start_stage_async("score", stages=rec.stages())
    try:
        assert entered.wait(10)
        with pytest.raises(RunInProgressError):
            run_stage("discover", stages=Recorder().stages(), conn=conn)
    finally:
        release.set()
        thread.join(15)
    assert rec.calls == ["score"]
    run_stage("discover", stages=Recorder().stages(), conn=conn)
