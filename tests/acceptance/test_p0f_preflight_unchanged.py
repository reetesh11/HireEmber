"""AC-12: dry-run and the apply utility modes run no settings check (green before and after)."""

import pytest
from p0f_helpers import World
from typer.testing import CliRunner

import hireember.cli as cli


@pytest.fixture
def w(monkeypatch, tmp_path, isolated_db):
    monkeypatch.setenv("COLUMNS", "300")
    return World(monkeypatch, tmp_path, isolated_db)


@pytest.fixture
def calls(monkeypatch):
    rec = {"pipeline": []}

    def fake_pipeline(*args, **kwargs):
        rec["pipeline"].append((args, kwargs))
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr("hireember.pipeline.run_pipeline", fake_pipeline)
    monkeypatch.setattr("hireember.apply.launcher.main", lambda *a, **k: None)
    monkeypatch.setattr("hireember.apply.launcher.mark_job", lambda *a, **k: None)
    monkeypatch.setattr("hireember.apply.launcher.reset_failed", lambda *a, **k: 0)
    return rec


def invoke(*args):
    return CliRunner().invoke(cli.app, list(args))


def test_ac12_run_dry_run_skips_the_check(w, calls):
    w.browser_installed = False
    res = invoke("run", "discover", "enrich", "--dry-run")
    assert res.exit_code == 0, res.output
    assert "Before this run" not in res.output and "need setting up" not in res.output
    assert len(calls["pipeline"]) == 1


@pytest.mark.parametrize("args", [
    ["--mark-applied", "https://j/1"],
    ["--mark-failed", "https://j/1", "--fail-reason", "x"],
    ["--reset-failed"],
    ["--dry-run"],
])
def test_ac12_apply_utility_modes_and_dry_run_skip_the_check(w, calls, args):
    w.chrome_installed = False
    res = invoke("apply", *args)
    assert "Before this run" not in res.output and "need setting up" not in res.output
    assert "Playwright" not in res.output
