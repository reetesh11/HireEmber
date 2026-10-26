"""Phase 6 AC-1 and AC-7: a log file per run and per ticket attempt, written safely, pruned at 90 days."""

import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from p6_helpers import Recorder, make_ticket, use_log_dir


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    return use_log_dir(monkeypatch, tmp_path)


# -- paths and the line writer ----------------------------------------------------

def test_log_paths_follow_the_contract(logdir):
    from hireember import logs

    assert logs.RETENTION_DAYS == 90
    assert logs.log_root() == logdir
    assert logs.run_log_path(7) == logdir / "runs" / "run-7.log"
    assert logs.attempt_log_path(3, 2) == logdir / "tickets" / "ticket-3-attempt-2.log"


def test_default_log_folder_is_under_the_data_folder_not_the_repo():
    from hireember import config, logs

    assert logs.log_root() == config.LOG_DIR
    assert config.LOG_DIR == config.APP_DIR / "logs"


def test_write_line_appends_timestamped_single_lines(logdir):
    from hireember import logs

    path = logs.run_log_path(1)
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert logs.write_line(path, "first\nsecond", "warn", now=when) is True
    assert logs.write_line(path, "third") is True
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert re.fullmatch(r"2026-01-02T03:04:05(\.0+)?(\+00:00|Z) \[warn\] first second", lines[0])
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\S+ \[info\] third", lines[1])
    assert logs.read_log(path) == path.read_text(encoding="utf-8")


def test_read_log_of_a_missing_file_is_none(logdir):
    from hireember import logs

    assert logs.read_log(logs.run_log_path(404)) is None


def test_write_line_redacts_secret_environment_values(logdir, monkeypatch):
    from hireember import logs

    monkeypatch.setenv("SOME_PROVIDER_KEY", "abcd1234efgh5678")
    monkeypatch.setenv("SOME_ACCESS_TOKEN", "tokenvalue987654")
    monkeypatch.setenv("SOME_CLIENT_SECRET", "secretvalue123456")
    monkeypatch.setenv("SHORT_KEY", "tiny")
    path = logs.run_log_path(2)
    logs.write_line(path, "x abcd1234efgh5678 y tokenvalue987654 z secretvalue123456 tiny")
    text = path.read_text(encoding="utf-8")
    for value in ("abcd1234efgh5678", "tokenvalue987654", "secretvalue123456"):
        assert value not in text
    assert text.count("[redacted]") == 3
    assert "tiny" in text  # values shorter than 8 characters are left alone


def test_unwritable_log_folder_returns_false_warns_once_and_never_raises(tmp_path, monkeypatch, capsys):
    import hireember.config as config
    from hireember import logs

    blocker = tmp_path / "blocker"
    blocker.write_text("a file, so no folder can be created beneath it")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")
    capsys.readouterr()
    assert logs.write_line(logs.run_log_path(1), "one") is False
    assert logs.write_line(logs.run_log_path(1), "two") is False
    err = capsys.readouterr().err
    assert err.count("Warning: could not write log") <= 1
    assert err == "" or err.lstrip().startswith("Warning: could not write log")


# -- run logs ---------------------------------------------------------------------

def test_run_log_exists_when_the_run_starts_and_records_events_and_the_end(conn, logdir):
    from hireember import logs, runs

    seen = {}

    def discover_hook(c, run_id):
        path = logs.run_log_path(run_id)
        seen["exists_at_start"] = path.exists()
        seen["first"] = path.read_text(encoding="utf-8").splitlines()[0]
        runs.log_event(c, run_id, "discover", "site timed out", "warning")

    rec = Recorder(found=7, scored=5, hooks={"discover": discover_hook})
    summary = runs.execute_run("scheduled", stages=rec.stages(), conn=conn)

    assert seen["exists_at_start"] is True
    assert seen["first"].endswith(f"run {summary.id} started (trigger: scheduled)")
    text = logs.read_log(logs.run_log_path(summary.id))
    lines = text.splitlines()
    assert any("[warning] discover: site timed out" in line for line in lines)
    assert lines[-1].endswith(f"run {summary.id} completed: found 7, scored 5")
    # the database copy of the event is unchanged
    assert runs.get_run_log(conn, summary.id)[0]["message"] == "site timed out"


def test_run_log_exists_even_when_every_stage_fails(conn, logdir):
    from hireember import logs, runs

    def boom(c, run_id):
        raise RuntimeError("stage exploded")

    rec = Recorder(hooks={n: boom for n in ("discover", "enrich", "score", "tailor")})
    summary = runs.execute_run("manual", stages=rec.stages(), conn=conn)
    assert summary.status == "partial"
    text = logs.read_log(logs.run_log_path(summary.id))
    assert text is not None
    assert "stage exploded" in text
    assert f"run {summary.id} partial:" in text.splitlines()[-1]


def test_each_run_writes_its_own_file(conn, logdir):
    from hireember import logs, runs

    a = runs.execute_run("manual", stages=Recorder().stages(), conn=conn)
    b = runs.execute_run("manual", stages=Recorder().stages(), conn=conn)
    assert a.id != b.id
    assert logs.run_log_path(a.id).exists() and logs.run_log_path(b.id).exists()
    assert f"run {b.id} started" not in logs.read_log(logs.run_log_path(a.id))


# -- ticket attempt logs ----------------------------------------------------------

def test_log_step_also_appends_to_the_attempt_log(conn, logdir):
    from hireember import logs
    from hireember.apply import attempts

    tid = make_ticket(conn, "a1")
    attempts.log_step(conn, tid, 1, "fill", field="email", source="profile", detail="typed")
    attempts.log_step(conn, tid, 1, "note")
    attempts.log_step(conn, tid, 2, "start", detail="http://127.0.0.1:9333")

    first = logs.read_log(logs.attempt_log_path(tid, 1)).splitlines()
    assert len(first) == 2
    assert first[0].endswith("fill | field=email | source=profile | typed")
    assert first[1].endswith("note")
    assert "field=" not in first[1] and "source=" not in first[1]
    second = logs.read_log(logs.attempt_log_path(tid, 2)).splitlines()
    assert second[0].endswith("start | http://127.0.0.1:9333")
    assert len(attempts.get_log(conn, tid)) == 3  # database rows unchanged


def test_apply_ticket_writes_an_attempt_log(conn, logdir, tmp_path):
    from hireember import logs
    from hireember.apply.runner import apply_ticket
    from p3_helpers import SESSION_LINK, add_ticket

    tid = add_ticket(conn, tmp_path, "ap1")
    apply_ticket(conn, tid, lambda session: None, session_link=SESSION_LINK)
    text = logs.read_log(logs.attempt_log_path(tid, 1))
    assert text is not None and "start" in text and SESSION_LINK in text


# -- AC-7: retention --------------------------------------------------------------

def _aged(path, now, days):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old\n", encoding="utf-8")
    stamp = (now - timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


def test_prune_logs_deletes_91_day_old_files_and_keeps_89_day_old_ones(logdir):
    from hireember import logs

    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    old_run, new_run = logs.run_log_path(1), logs.run_log_path(2)
    old_att, new_att = logs.attempt_log_path(1, 1), logs.attempt_log_path(1, 2)
    worker = logdir / "worker-0.log"
    for path, days in ((old_run, 91), (new_run, 89), (old_att, 91), (new_att, 89), (worker, 200)):
        _aged(path, now, days)

    assert logs.prune_logs(now=now) == 2
    assert not old_run.exists() and not old_att.exists()
    assert new_run.exists() and new_att.exists()
    assert worker.exists()  # other files in the log folder are left alone
    assert logs.prune_logs(now=now) == 0


def test_prune_logs_honours_max_age_days_and_never_raises_without_a_folder(tmp_path, monkeypatch):
    import hireember.config as config
    from hireember import logs

    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "nothing-here")
    assert logs.prune_logs() == 0
    root = use_log_dir(monkeypatch, tmp_path)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    _aged(logs.run_log_path(1), now, 10)
    assert logs.prune_logs(max_age_days=7, now=now) == 1
    assert root.exists()


def test_a_new_run_prunes_old_logs_and_keeps_its_records(conn, logdir):
    from hireember import logs, runs

    first = runs.execute_run("manual", stages=Recorder().stages(), conn=conn)
    old = logs.run_log_path(first.id)
    _aged(old, datetime.now(timezone.utc), 91)
    fresh = logs.run_log_path(first.id + 100)
    _aged(fresh, datetime.now(timezone.utc), 89)
    second = runs.execute_run("manual", stages=Recorder().stages(), conn=conn)
    assert not old.exists()
    assert fresh.exists()
    assert logs.run_log_path(second.id).exists()
    assert runs.get_run(conn, first.id) is not None  # the run record remains
