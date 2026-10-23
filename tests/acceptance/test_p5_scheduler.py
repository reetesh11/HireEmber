"""Phase 5 scheduler: schedule settings, test-clock ticks, missed runs, scheduled applying
(AC-1, AC-2, AC-3, AC-10, AC-11, AC-13)."""

import threading
from pathlib import Path

import pytest

from p5_helpers import Recorder, blocking_stages, make_ticket, run_rows, utc

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


@pytest.mark.parametrize("value,expected", [("08:00", "08:00"), ("8:05", "08:05"), ("23:59", "23:59"),
                                            ("00:00", "00:00")])
def test_parse_time_valid(value, expected):
    from hireember.scheduler import parse_time

    assert parse_time(value) == expected


@pytest.mark.parametrize("value", ["25:00", "8am", "12:60", "", "noon", "24:00"])
def test_parse_time_invalid(value):
    from hireember.scheduler import ScheduleError, parse_time

    with pytest.raises(ScheduleError) as exc:
        parse_time(value)
    assert str(exc.value) == f'Invalid time "{value}". Use 24-hour HH:MM, e.g. 08:00.'
    assert isinstance(exc.value, ValueError)


def test_set_get_clear_schedule(conn):
    from hireember.scheduler import clear_schedule, get_schedule, set_schedule

    s = get_schedule(conn)
    assert s.times == [] and s.apply is False and s.apply_limit == 25
    s = set_schedule(conn, ["18:30", "08:00", "08:00"], now=utc(2026, 3, 1, 6))
    assert s.times == ["08:00", "18:30"]
    assert get_schedule(conn).times == ["08:00", "18:30"]
    set_schedule(conn, ["09:15"], now=utc(2026, 3, 1, 6))
    assert get_schedule(conn).times == ["09:15"]
    clear_schedule(conn)
    assert get_schedule(conn).times == []


def test_set_schedule_invalid_leaves_old_schedule(conn):
    from hireember.scheduler import ScheduleError, get_schedule, set_schedule

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 6))
    with pytest.raises(ScheduleError):
        set_schedule(conn, ["09:00", "25:00"], now=utc(2026, 3, 1, 6))
    assert get_schedule(conn).times == ["08:00"]


def test_set_apply(conn):
    from hireember.scheduler import get_schedule, set_apply

    set_apply(conn, on=True, limit=5)
    s = get_schedule(conn)
    assert s.apply is True and s.apply_limit == 5
    set_apply(conn, on=False)
    s = get_schedule(conn)
    assert s.apply is False and s.apply_limit == 5
    with pytest.raises(ValueError):
        set_apply(conn, limit=0)


def test_tick_without_schedule_does_nothing(conn):
    from hireember.scheduler import tick

    rec = Recorder()
    assert tick(conn, utc(2026, 3, 1, 12), stages=rec.stages()) is None
    assert rec.calls == [] and run_rows(conn) == []


def test_scheduled_run_fires_once_at_set_time(conn):
    """AC-1: advancing the test clock to 08:00 starts exactly one scheduled run."""
    from hireember.scheduler import set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7, 0))
    rec = Recorder(found=9, scored=6, skipped=3)
    assert tick(conn, utc(2026, 3, 1, 7, 59), stages=rec.stages()) is None
    assert run_rows(conn) == []
    summary = tick(conn, utc(2026, 3, 1, 8, 0), stages=rec.stages())
    assert summary is not None and summary.trigger == "scheduled"
    rows = run_rows(conn)
    assert len(rows) == 1
    assert (summary.found, summary.scored, summary.skipped) == (9, 6, 3)
    assert isinstance(summary.tickets_created, int) and isinstance(summary.tickets_blocked, int)
    assert tick(conn, utc(2026, 3, 1, 9, 30), stages=rec.stages()) is None
    assert tick(conn, utc(2026, 3, 1, 23, 59), stages=rec.stages()) is None
    assert len(run_rows(conn)) == 1
    # next day fires again
    assert tick(conn, utc(2026, 3, 2, 8, 1), stages=rec.stages()) is not None
    assert len(run_rows(conn)) == 2


def test_due_slot(conn):
    from hireember.scheduler import due_slot, set_schedule

    assert due_slot(conn, utc(2026, 3, 1, 12)) is None
    set_schedule(conn, ["08:00", "18:30"], now=utc(2026, 3, 1, 7))
    assert due_slot(conn, utc(2026, 3, 1, 7, 30)) is None
    assert due_slot(conn, utc(2026, 3, 1, 9)) == utc(2026, 3, 1, 8)
    assert due_slot(conn, utc(2026, 3, 1, 19)) == utc(2026, 3, 1, 18, 30)


def test_slots_before_schedule_was_set_do_not_fire(conn):
    from hireember.scheduler import set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 9))
    rec = Recorder()
    assert tick(conn, utc(2026, 3, 1, 10), stages=rec.stages()) is None
    assert rec.calls == []


def test_missed_slots_start_exactly_one_run(conn):
    """AC-10: the machine was off for several slots; the next start launches one run."""
    from hireember.scheduler import set_schedule, tick

    set_schedule(conn, ["08:00", "18:00"], now=utc(2026, 3, 1, 10))
    rec = Recorder()
    summary = tick(conn, utc(2026, 3, 4, 12), stages=rec.stages())
    assert summary is not None and summary.trigger == "scheduled"
    assert len(run_rows(conn)) == 1
    assert tick(conn, utc(2026, 3, 4, 12, 1), stages=rec.stages()) is None
    assert len(run_rows(conn)) == 1


def test_overlapping_scheduler_trigger_makes_no_row(conn):
    """AC-2: a tick while a run is in progress starts nothing and consumes its slot."""
    from hireember.runs import execute_run
    from hireember.scheduler import set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7))
    entered, release = threading.Event(), threading.Event()
    t = threading.Thread(
        target=lambda: execute_run("manual", stages=blocking_stages(entered, release).stages()),
        daemon=True)
    t.start()
    try:
        assert entered.wait(10)
        rec = Recorder()
        assert tick(conn, utc(2026, 3, 1, 8), stages=rec.stages()) is None
        assert rec.calls == []
    finally:
        release.set()
        t.join(15)
    assert len(run_rows(conn)) == 1


def test_scheduled_run_never_applies_by_default(conn):
    """AC-3: applying off means the apply stage (and so the browser launcher) is not called."""
    from hireember.scheduler import set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7))
    rec = Recorder()
    assert tick(conn, utc(2026, 3, 1, 8), stages=rec.stages()) is not None
    assert "apply" not in rec.calls


def test_scheduled_apply_respects_remaining_daily_limit(conn):
    """AC-11: limit minus applications already made today."""
    from hireember.scheduler import set_apply, set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7))
    set_apply(conn, on=True, limit=3)
    for i in range(2):
        make_ticket(conn, f"done{i}", status="applied", submitted_at="2026-03-01T06:00:00+00:00")
    make_ticket(conn, "yesterday", status="applied", submitted_at="2026-02-28T06:00:00+00:00")
    rec = Recorder()
    assert tick(conn, utc(2026, 3, 1, 8), stages=rec.stages()) is not None
    assert rec.calls[-1] == "apply" and rec.apply_limits == [1]


def test_scheduled_apply_skipped_when_limit_reached(conn):
    from hireember.scheduler import set_apply, set_schedule, tick

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7))
    set_apply(conn, on=True, limit=2)
    for i in range(2):
        make_ticket(conn, f"done{i}", status="applied", submitted_at="2026-03-01T06:00:00+00:00")
    rec = Recorder()
    summary = tick(conn, utc(2026, 3, 1, 8), stages=rec.stages())
    assert summary is not None and summary.status == "completed"
    assert "apply" not in rec.calls


def test_serve_once_runs_due_slot(conn):
    from hireember.scheduler import serve, set_schedule

    set_schedule(conn, ["08:00"], now=utc(2026, 3, 1, 7))
    rec = Recorder()
    serve(once=True, clock=lambda: utc(2026, 3, 1, 8, 5), stages=rec.stages())
    assert len(run_rows(conn)) == 1


def test_readme_documents_scheduled_and_missed_runs():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Scheduled runs" in text
    section = text[text.index("Scheduled runs"):].lower()
    assert "missed" in section and "next start" in section
