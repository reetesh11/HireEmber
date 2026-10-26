"""CLI single-stage run and the apply lock/summary line."""

from typer.testing import CliRunner

import pytest

from hireember import preflight, runs
from hireember.cli import app


@pytest.fixture(autouse=True)
def _preflight_ok(monkeypatch):
    monkeypatch.setattr(preflight, "run_preflight",
                        lambda *a, **k: preflight.PreflightOutcome(proceed=True, stages=["discover"]))


def _out(result):
    return " ".join(result.output.split())


def test_run_single_stage_prints_message(isolated_db, monkeypatch):
    seen = {}

    def fake(stage, **kw):
        seen["stage"] = stage
        return runs.StageResult(stage, "discover: 3 roles found, 1 new.", {})

    monkeypatch.setattr(runs, "run_stage", fake)
    r = CliRunner().invoke(app, ["run", "discover"])
    assert r.exit_code == 0, r.output
    assert "discover: 3 roles found, 1 new." in _out(r) and seen["stage"] == "discover"


def test_run_single_stage_busy(isolated_db, monkeypatch):
    def busy(stage, **kw):
        raise runs.RunInProgressError()

    monkeypatch.setattr(runs, "run_stage", busy)
    r = CliRunner().invoke(app, ["run", "discover"])
    assert r.exit_code == 1 and "A run is already in progress." in _out(r)


def test_run_single_stage_busy_checked_before_preflight(isolated_db, monkeypatch):
    from hireember.database import get_connection, init_db

    token = runs.acquire_lock(init_db())
    monkeypatch.setattr(preflight, "run_preflight", lambda *a, **k: 1 / 0)
    r = CliRunner().invoke(app, ["run", "score"])
    assert r.exit_code == 1 and "A run is already in progress." in _out(r)
    runs.release_lock(get_connection(), token)
