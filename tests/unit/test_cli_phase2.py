"""CLI for answers, queue, resumes and status (implementation tests)."""

import pytest
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from hireember.database import close_connection, init_db


@pytest.fixture
def env(tmp_path, isolated_db, monkeypatch):
    monkeypatch.setattr(cli, "console", Console(width=250))
    conn = init_db(isolated_db)
    conn.execute("INSERT INTO jobs (url, title, site) VALUES ('https://j/1', 'T', 'S')")
    conn.commit()
    yield conn
    close_connection(isolated_db)


def test_empty_listings(env):
    runner = CliRunner()
    assert "No answers stored yet" in runner.invoke(cli.app, ["answers", "list"]).output
    assert "No open queue items." in runner.invoke(cli.app, ["queue", "list"]).output


def test_queue_answer_unknown_item_exits_1(env):
    res = CliRunner().invoke(cli.app, ["queue", "answer", "9", "x"])
    assert res.exit_code == 1 and "Queue item 9 not found or already resolved." in res.output


def test_status_lists_blocked_tickets(env):
    from hireember.tickets import open_ticket

    open_ticket(env, "https://j/1", "blocked for human", 'validation failed: employer "Acme Corp" not in resume facts')
    out = CliRunner().invoke(cli.app, ["status"]).output
    assert "Tickets needing attention" in out
    assert 'validation failed: employer "Acme Corp" not in resume facts' in out
