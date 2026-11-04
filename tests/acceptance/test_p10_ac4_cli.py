"""Phase 10 AC-4, AC-5, AC-10 at the CLI: hireember add-job."""

import pytest
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from p10_helpers import Pipeline, job_count, job_page_for, simple_html, ticket_of

U1, U2, U3 = "https://example.com/jobs/1", "https://example.com/jobs/2", "https://example.com/jobs/3"


@pytest.fixture
def env(isolated_db, monkeypatch):
    from hireember import config
    from hireember.database import close_connection, init_db

    monkeypatch.setattr(cli, "console", Console(width=300))
    monkeypatch.setenv("COLUMNS", "300")
    conn = init_db(isolated_db)
    config.ensure_dirs()
    yield conn
    close_connection(isolated_db)


def run(*args):
    return CliRunner().invoke(cli.app, ["add-job", *args], env={"COLUMNS": "300"})


def test_without_apply_makes_no_launcher_call(env, monkeypatch):
    job_page_for(monkeypatch, default_html=simple_html(1))
    p = Pipeline(monkeypatch)
    result = run(U1, U2)
    assert result.exit_code == 0, result.output
    assert p.launches == [] and not [c for c in p.calls if c[0] in ("preflight", "launch")]
    assert "Stopped at ticket (run with --apply to apply)" in result.output


def test_apply_launches_exactly_the_added_urls(env, monkeypatch):
    from p10_helpers import make_ticket

    make_ticket(env, "dup", status="pending")
    job_page_for(monkeypatch, {U1: simple_html(1), U3: simple_html(3)}, fail={U2: "The page was not found (404)."})
    p = Pipeline(monkeypatch)
    result = run(U1, U2, "https://jobs.example/dup", U3, "--apply")
    assert result.exit_code == 0, result.output
    assert p.launched_urls == [U1, U3]
    assert p.launches[0]["review"] is True
    assert p.calls.index(("preflight", "apply")) < p.calls.index(("launch", U1))


def test_no_review_passes_review_false_and_is_not_saved(env, monkeypatch):
    job_page_for(monkeypatch, default_html=simple_html(1))
    p = Pipeline(monkeypatch)
    before = [tuple(r) for r in env.execute("SELECT key, value FROM settings WHERE key != 'add_jobs_state' ORDER BY key")]
    result = run(U1, "--apply", "--no-review")
    assert result.exit_code == 0, result.output
    assert p.launches[0]["review"] is False
    after = [tuple(r) for r in env.execute("SELECT key, value FROM settings WHERE key != 'add_jobs_state' ORDER BY key")]
    assert before == after
    result = run(U2, "--apply")
    assert p.launches[-1]["review"] is True


@pytest.mark.parametrize("key", ["review", "review_mode", "no_review", "review_off"])
def test_saved_setting_cannot_turn_review_off(env, monkeypatch, key):
    from hireember import tickets

    tickets.set_setting(env, key, "off")
    monkeypatch.setenv("HIREEMBER_REVIEW", "0")
    monkeypatch.setenv("HIREEMBER_NO_REVIEW", "1")
    job_page_for(monkeypatch, default_html=simple_html(1))
    p = Pipeline(monkeypatch)
    assert run(U1, "--apply").exit_code == 0
    assert p.launches[0]["review"] is True


def test_no_review_without_apply_exits_2(env, monkeypatch):
    p = Pipeline(monkeypatch)
    result = run(U1, "--no-review")
    assert result.exit_code == 2 and "--no-review needs --apply." in result.output
    assert job_count(env) == 0 and p.launches == []


def test_no_url_is_a_usage_error(env):
    result = run()
    assert result.exit_code == 2 and "Missing argument" in result.output


def test_nothing_new_to_apply_to(env, monkeypatch):
    job_page_for(monkeypatch, fail={U1: "The page was not found (404)."})
    p = Pipeline(monkeypatch)
    result = run(U1, "--apply")
    assert result.exit_code == 0 and "Nothing new to apply to." in result.output
    assert p.launches == []


def test_table_and_summary_for_three_urls_one_failing(env, monkeypatch):
    job_page_for(monkeypatch, {U1: simple_html(1), U3: simple_html(3)}, fail={U2: "The page was not found (404)."})
    Pipeline(monkeypatch)
    result = run(U1, U2, U3)
    out = result.output
    assert result.exit_code == 0, out
    for header in ("URL", "Result", "Ticket", "Score", "Next step"):
        assert header in out
    assert "3 URLs: 2 added, 0 already added, 1 failed." in out
    assert out.index(U1) < out.index(U2) < out.index(U3)
    t1, t3 = ticket_of(env, U1), ticket_of(env, U3)
    assert f"#{t1['id']}" in out and f"#{t3['id']}" in out and f"#{ticket_of(env, U2)['id']}" in out
    assert "failed" in out and "Blocked for human: The page was not found (404)." in out


def test_same_url_twice_gives_added_and_already_added(env, monkeypatch):
    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    result = run(U1, U1)
    assert "1 added, 1 already added, 0 failed" in result.output and job_count(env) == 1


def test_run_in_progress_is_refused(env, monkeypatch):
    from hireember import runs

    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    token = runs.acquire_lock(env)
    try:
        result = run(U1)
    finally:
        runs.release_lock(env, token)
    assert result.exit_code == 1
    assert "A run is already in progress. Wait for it to finish, then try again." in result.output
    assert job_count(env) == 0
    assert run(U1).exit_code == 0 and not runs.is_running(env)


def test_help_lists_options_and_mentions_adding_by_url():
    out = CliRunner().invoke(cli.app, ["add-job", "--help"], env={"COLUMNS": "200"}).output
    for opt in ("--apply", "--no-review", "--text"):
        assert opt in out
