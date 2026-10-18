import pytest
from typer.testing import CliRunner

from hireember.apply.attempts import log_step
from hireember.cli import app
from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import set_job_score


@pytest.fixture
def conn(isolated_db):
    c = init_db()
    store_jobs(c, [{"url": "u1", "title": "T", "company": "Acme", "location": "X"}], "S", "t")
    yield c
    close_connection()


def test_ticket_log_shows_rows(conn):
    tid = set_job_score(conn, "u1", 8)
    log_step(conn, tid, 1, "fill", "Full name", "profile:full_name", "Test")
    result = CliRunner().invoke(app, ["ticket", "log", str(tid)])
    assert result.exit_code == 0
    assert "profile:full_name" in result.output


def test_ticket_log_empty_and_unknown(conn):
    tid = set_job_score(conn, "u1", 8)
    empty = CliRunner().invoke(app, ["ticket", "log", str(tid)])
    missing = CliRunner().invoke(app, ["ticket", "log", "999"])
    assert f"No attempts logged for ticket {tid}." in empty.output
    assert missing.exit_code == 1 and "Ticket 999 not found." in missing.output


def test_company_manual_and_list(conn):
    runner = CliRunner()
    on = runner.invoke(app, ["company", "manual", "acme"])
    assert on.exit_code == 0 and 'Company "acme" is now manual-only.' in on.output
    listed = runner.invoke(app, ["company", "list"])
    assert "Acme" in listed.output and "yes" in listed.output
    off = runner.invoke(app, ["company", "manual", "acme", "--off"])
    assert 'Company "acme" is no longer manual-only.' in off.output
    bad = runner.invoke(app, ["company", "manual", "Nobody"])
    assert bad.exit_code == 1 and 'No company named "Nobody".' in bad.output
