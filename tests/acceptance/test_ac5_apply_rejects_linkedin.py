"""AC-5: the apply stage rejects LinkedIn jobs before Chrome or Claude Code start."""

import atexit
import logging
import signal

import pytest
from typer.testing import CliRunner

import hireember.apply.chrome as chrome_mod
from hireember import config, database
from hireember.apply import dashboard, launcher
from hireember.cli import app

# Importing the launcher registers a Chrome/CDP-port sweep at interpreter exit;
# no Chrome is started by these tests, so keep the developer's browser alone.
atexit.unregister(chrome_mod.cleanup_on_exit)

LINKEDIN_URL = "https://www.linkedin.com/jobs/view/123"


@pytest.fixture
def spawn_calls(monkeypatch):
    """Record any attempt to launch Chrome, run a job, or start a subprocess."""
    calls: list[str] = []

    def fake_launch_chrome(*args, **kwargs):
        calls.append("launch_chrome")

    def fake_run_job(*args, **kwargs):
        calls.append("run_job")
        return "failed:stubbed", 0

    def fake_popen(*args, **kwargs):
        calls.append("subprocess.Popen")
        raise RuntimeError("subprocess.Popen must not be called")

    monkeypatch.setattr(launcher, "launch_chrome", fake_launch_chrome)
    monkeypatch.setattr(launcher, "run_job", fake_run_job)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)
    return calls


@pytest.fixture
def restore_sigint():
    previous = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGINT, previous)


def _output(result) -> str:
    text = result.output or ""
    try:
        text += result.stderr or ""
    except (ValueError, AttributeError):
        pass
    return " ".join(text.split())


@pytest.mark.parametrize("extra_args", [[], ["--gen"]], ids=["apply", "apply-gen"])
def test_cli_apply_rejects_linkedin_url(extra_args, spawn_calls, isolated_db):
    result = CliRunner().invoke(app, ["apply", "--url", LINKEDIN_URL, *extra_args])

    assert result.exit_code == 1, _output(result)
    assert f"LinkedIn job URLs are not supported: {LINKEDIN_URL}" in _output(result)
    assert spawn_calls == []
    assert not isolated_db.exists(), "the database was opened before the LinkedIn check"


def test_launcher_main_rejects_linkedin_url(spawn_calls, isolated_db, restore_sigint):
    blocked_error = config.LinkedInBlockedError
    assert issubclass(blocked_error, ValueError)

    with pytest.raises(blocked_error) as excinfo:
        launcher.main(limit=1, target_url=LINKEDIN_URL)

    assert "LinkedIn" in str(excinfo.value)
    assert LINKEDIN_URL in str(excinfo.value)
    assert spawn_calls == []


def test_gen_prompt_rejects_linkedin_url_before_db(spawn_calls, isolated_db):
    blocked_error = config.LinkedInBlockedError

    with pytest.raises(blocked_error):
        launcher.gen_prompt(LINKEDIN_URL)

    assert spawn_calls == []
    assert not isolated_db.exists(), "gen_prompt touched the database"


def test_worker_loop_blocks_queued_linkedin_job(spawn_calls, isolated_db, caplog):
    conn = database.init_db()
    job_url = "https://www.indeed.com/viewjob?jk=linkedin-apply"
    conn.execute(
        "INSERT INTO jobs (url, title, site, application_url, tailored_resume_path, fit_score) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_url, "Backend Engineer", "indeed", "https://www.linkedin.com/jobs/view/789",
         "/tmp/tailored_resume.pdf", 9),
    )
    conn.commit()
    dashboard.init_worker(0)
    caplog.set_level(logging.WARNING)

    result = launcher.worker_loop(worker_id=0, limit=1, min_score=7)

    assert result == (0, 0)
    assert spawn_calls == []
    row = conn.execute(
        "SELECT apply_status, apply_error, apply_attempts FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()
    assert row["apply_status"] == "failed"
    assert row["apply_error"] == "linkedin_blocked: LinkedIn jobs are not supported"
    assert row["apply_attempts"] == 99
    assert any(
        r.levelno >= logging.WARNING and "LinkedIn" in r.getMessage() for r in caplog.records
    ), "no WARNING mentioning LinkedIn was logged"
