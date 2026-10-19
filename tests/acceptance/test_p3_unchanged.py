"""Phase 3: behaviour that must not change."""

import json

import pytest

from p3_helpers import make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def test_job_without_a_ticket_row_can_still_be_acquired(env):
    from hireember.apply import launcher

    conn, _ = env
    conn.execute(
        "INSERT INTO jobs (url, title, site, application_url, tailored_resume_path, fit_score) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("https://jobs.example/plain", "Backend Engineer", "indeed", "https://jobs.example/plain/apply",
         "/tmp/tailored_resume.pdf", 9),
    )
    conn.commit()

    job = launcher.acquire_job(min_score=7)

    assert job is not None and job["url"] == "https://jobs.example/plain"


def test_apply_command_keeps_its_existing_options():
    from typer.testing import CliRunner

    from hireember.cli import app

    result = CliRunner().invoke(app, ["apply", "--help"])

    assert result.exit_code == 0
    for option in ("--limit", "--workers", "--min-score", "--model", "--continuous", "--dry-run",
                   "--headless", "--url", "--gen", "--mark-applied", "--mark-failed", "--reset-failed"):
        assert option in result.output


def test_existing_queue_answer_command_still_works(env):
    from typer.testing import CliRunner

    from hireember.answers import match_answer
    from hireember.cli import app
    from hireember.tickets import get_ticket
    from p3_helpers import add_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "n1")
    item = match_answer(conn, tid, "What is your favourite colour?").queue_item_id

    result = CliRunner().invoke(app, ["queue", "answer", str(item), "Blue"])

    assert result.exit_code == 0, result.output
    assert f"Answer saved. Ticket {tid} is ready to resume." in result.output
    assert get_ticket(conn, tid)["status"] == "pending"
    assert json.dumps(True)
