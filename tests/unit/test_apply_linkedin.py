"""Unit tests: the apply stage rejects LinkedIn jobs."""

import atexit

import pytest
from typer.testing import CliRunner

import applypilot.apply.chrome as chrome_mod
from applypilot import config
from applypilot.apply import dashboard, launcher
from applypilot.cli import app

# No Chrome is started here; don't sweep the developer's browser at exit.
atexit.unregister(chrome_mod.cleanup_on_exit)

LINKEDIN_URL = "https://uk.linkedin.com/jobs/view/42"


def test_gen_prompt_raises_for_linkedin():
    with pytest.raises(config.LinkedInBlockedError):
        launcher.gen_prompt(LINKEDIN_URL)


def test_worker_loop_target_mode_stops_after_linkedin_job(monkeypatch):
    job = {
        "url": "https://www.indeed.com/viewjob?jk=9",
        "application_url": LINKEDIN_URL,
        "title": "Engineer",
        "site": "indeed",
    }
    acquired = []
    marked = []

    def fake_acquire(**kwargs):
        acquired.append(kwargs)
        return dict(job) if len(acquired) == 1 else None

    def forbidden(*args, **kwargs):
        raise AssertionError("must not be called for a LinkedIn job")

    monkeypatch.setattr(launcher, "acquire_job", fake_acquire)
    monkeypatch.setattr(launcher, "mark_result", lambda *a, **k: marked.append((a, k)))
    monkeypatch.setattr(launcher, "launch_chrome", forbidden)
    monkeypatch.setattr(launcher, "run_job", forbidden)
    dashboard.init_worker(0)

    result = launcher.worker_loop(worker_id=0, limit=5, target_url=job["url"])

    assert result == (0, 0)
    assert len(acquired) == 1
    assert marked == [
        ((job["url"], "failed", "linkedin_blocked: LinkedIn jobs are not supported"), {"permanent": True})
    ]


def test_cli_apply_gen_linkedin_exits_1():
    result = CliRunner().invoke(app, ["apply", "--gen", "--url", LINKEDIN_URL])
    assert result.exit_code == 1
    assert "LinkedIn job URLs are not supported" in result.output
