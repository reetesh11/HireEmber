"""Ticket notes and referral notes (implementation tests)."""

import pytest

from hireember import tickets
from hireember.database import close_connection, init_db


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    conn.execute("INSERT INTO jobs (url, title, site) VALUES ('https://j/1', 'T', 'S')")
    conn.commit()
    tid = tickets.set_job_score(conn, "https://j/1", 8, "ok")
    yield conn, tid
    close_connection(db)


def test_note_and_referral_note_write_one_event_each(env):
    conn, tid = env
    before = len(tickets.get_history(conn, tid))
    tickets.set_note(conn, tid, "hello")
    tickets.set_note(conn, tid, "via Sam", kind="referral note")
    t = tickets.get_ticket(conn, tid)
    assert (t["notes"], t["referral_note"], t["status"]) == ("hello", "via Sam", "pending")
    hist = tickets.get_history(conn, tid)[before:]
    assert [(h["actor"], h["reason"]) for h in hist] == [("user", "note"), ("user", "referral note")]


def test_clear_and_errors(env):
    conn, tid = env
    tickets.set_note(conn, tid, "x")
    tickets.set_note(conn, tid, "")
    assert tickets.get_ticket(conn, tid)["notes"] == ""
    before = len(tickets.get_history(conn, tid))
    with pytest.raises(tickets.NoteTooLongError):
        tickets.set_note(conn, tid, "x" * 10001)
    tickets.set_note(conn, tid, "x" * 10000)
    with pytest.raises(tickets.TicketNotFoundError):
        tickets.set_note(conn, 999, "x")
    assert len(tickets.get_history(conn, tid)) == before + 1
