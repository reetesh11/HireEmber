"""schedule and scheduler commands."""

from typer.testing import CliRunner

from hireember.cli import app


def _run(*args):
    result = CliRunner().invoke(app, list(args))
    return result, " ".join(result.output.split())


def test_apply_limit_must_be_positive(isolated_db):
    r, out = _run("schedule", "--apply-limit", "0")
    assert r.exit_code == 1 and "at least 1" in out


def test_default_status(isolated_db):
    r, out = _run("schedule")
    assert "No schedule set." in out and "Scheduled applying: off." in out


def test_scheduler_once_without_schedule(isolated_db):
    r, out = _run("scheduler", "--once")
    assert r.exit_code == 0 and "Scheduler running" not in out
