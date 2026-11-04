"""Phase 10 AC-8 at the CLI: add-job URL --text FILE."""

import pytest
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from p10_helpers import Pipeline, job_count, job_page_for, job_row, ticket_of

URL = "https://example.com/careers/closed"
TEXT = "Staff Engineer\nYou will lead a small team building payment systems in Python and Go every day."


@pytest.fixture
def env(isolated_db, monkeypatch):
    from hireember import config
    from hireember.database import close_connection, init_db

    monkeypatch.setattr(cli, "console", Console(width=300))
    conn = init_db(isolated_db)
    config.ensure_dirs()
    yield conn
    close_connection(isolated_db)


def run(*args):
    return CliRunner().invoke(cli.app, ["add-job", *args], env={"COLUMNS": "300"})


def test_text_file_resumes_a_blocked_url(env, monkeypatch, tmp_path):
    job_page_for(monkeypatch, fail={URL: "The page was not found (404)."})
    p = Pipeline(monkeypatch)
    first = run(URL)
    assert first.exit_code == 0
    blocked = ticket_of(env, URL)
    assert blocked["status"] == "blocked for human"
    f = tmp_path / "desc.txt"
    f.write_text(TEXT, encoding="utf-8")
    second = run(URL, "--text", str(f))
    assert second.exit_code == 0, second.output
    assert job_count(env) == 1 and ticket_of(env, URL)["id"] == blocked["id"]
    assert "payment systems" in job_row(env, URL)["full_description"]
    assert [c[0] for c in p.calls] == ["score", "tailor"]


def test_text_with_two_urls_exits_2(env, tmp_path):
    f = tmp_path / "desc.txt"
    f.write_text(TEXT, encoding="utf-8")
    result = run(URL, "https://example.com/b", "--text", str(f))
    assert result.exit_code == 2 and "--text works with one URL at a time." in result.output
    assert job_count(env) == 0


def test_empty_file(env, tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("  \n", encoding="utf-8")
    result = run(URL, "--text", str(f))
    assert result.exit_code == 1 and "The description file is empty." in result.output
    assert job_count(env) == 0


def test_unreadable_file(env, tmp_path):
    result = run(URL, "--text", str(tmp_path / "missing.txt"))
    assert result.exit_code == 1 and "The description file could not be read." in result.output
    assert job_count(env) == 0
