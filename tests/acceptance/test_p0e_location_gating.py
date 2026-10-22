"""AC-7, AC-9, AC-12, AC-13: location pre-skip at scoring time, prompt line, status and ticket log."""

import re

import pytest
from p0e_helpers import FakeClient
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from hireember import config, gating, tickets
from hireember.database import close_connection, get_stats, init_db, store_jobs
from hireember.resumes import add_resume

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
SOURCES = [("indeed", "jobspy"), ("Workday TD", "workday_api"), ("Acme Careers", "json_ld")]
SENTENCE = "A job whose location is incompatible with the candidate's target locations is a reason for a low score."


@pytest.fixture
def env(tmp_path, isolated_db, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "absent-searches.yaml")
    monkeypatch.setattr(cli, "console", Console(width=300))
    monkeypatch.setenv("COLUMNS", "300")
    conn = init_db(isolated_db)
    config.ensure_dirs()
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    add_resume(conn, f, "Base", "python")
    client = FakeClient("SCORE: 9\nKEYWORDS: a\nREASONING: Great.")
    monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: client)
    yield conn, client
    close_connection(isolated_db)


def _add(conn, url, location, site="indeed", strategy="jobspy"):
    store_jobs(conn, [{"url": url, "title": "Python Dev", "company": "Acme", "location": location}], site, strategy)
    conn.execute("UPDATE jobs SET full_description = 'desc' WHERE url = ?", (url,))
    conn.commit()


@pytest.mark.parametrize("site, strategy", SOURCES, ids=["jobspy", "workday", "smart-extract"])
def test_ac7_ac9_outside_location_is_skipped_without_llm_call(env, site, strategy):
    conn, client = env
    _add(conn, "https://j/1", "Austin, TX", site, strategy)
    result = gating.score_job_for_ticket(conn, "https://j/1", profile=PROFILE)
    assert result.status == "skipped"
    assert result.reason == "location: Austin, TX"
    assert result.score is None
    assert client.calls == 0
    t = tickets.get_ticket(conn, result.ticket_id)
    assert (t["status"], t["status_reason"]) == ("skipped", "location: Austin, TX")
    events = conn.execute("SELECT COUNT(*) FROM ticket_events WHERE ticket_id = ?", (result.ticket_id,)).fetchone()[0]
    assert events >= 1


def test_ac12_scoring_prompt_has_location_instruction():
    from hireember.scoring.scorer import SCORE_PROMPT

    assert SENTENCE in SCORE_PROMPT


def test_run_scoring_counts_location_skips_not_errors(env, monkeypatch):
    from hireember.scoring import scorer

    conn, client = env
    _add(conn, "https://j/1", "Austin, TX")
    _add(conn, "https://j/2", "Toronto, ON")
    monkeypatch.setattr(scorer, "load_profile", lambda: PROFILE)
    result = scorer.run_scoring()
    assert result["location_skipped"] == 1
    assert result["scored"] == 1 and result["errors"] == 0
    assert client.calls == 1


def test_ac13_stats_status_and_ticket_log_show_the_reason(env):
    conn, _ = env
    _add(conn, "https://j/1", "Berlin, Germany")
    _add(conn, "https://j/2", "Paris, France")
    _add(conn, "https://j/3", "Toronto, ON")
    t1 = tickets.open_ticket(conn, "https://j/1", "skipped", "location: Berlin, Germany")
    tickets.open_ticket(conn, "https://j/2", "skipped", "location: Paris, France")
    tickets.open_ticket(conn, "https://j/3", "skipped", "score 3 below threshold 7")
    assert get_stats(conn)["location_skipped"] == 2

    status = CliRunner().invoke(cli.app, ["status"])
    assert status.exit_code == 0, status.output
    row = [ln for ln in status.output.splitlines() if "Skipped by location" in ln]
    assert row and re.search(r"\b2\b", row[0]), status.output

    log = CliRunner().invoke(cli.app, ["ticket", "log", str(t1)])
    assert log.exit_code == 0, log.output
    assert "Status: skipped (location: Berlin, Germany)" in log.output
    assert f"No attempts logged for ticket {t1}." in log.output
