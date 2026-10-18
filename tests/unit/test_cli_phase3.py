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
