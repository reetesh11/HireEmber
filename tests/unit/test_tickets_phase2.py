import pytest

from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import (
    TicketError,
    get_history,
    get_ticket,
    open_ticket,
    set_ticket_files,
    set_ticket_resume,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    store_jobs(c, [{"url": "u1", "title": "T", "company": "Acme"}], "S", "t")
    yield c
    close_connection(db)


def test_open_ticket_is_idempotent_and_unscored(conn):
    a = open_ticket(conn, "u1", "blocked for human", "no base resume")
    assert open_ticket(conn, "u1") == a
    t = get_ticket(conn, a)
    assert t["status"] == "blocked for human" and t["score"] is None
    assert [e["reason"] for e in get_history(conn, a)] == ["no base resume"]
    with pytest.raises(TicketError):
        open_ticket(conn, "missing")


def test_set_resume_and_files(conn):
    a = open_ticket(conn, "u1")
    set_ticket_resume(conn, a, 3)
    set_ticket_files(conn, a, "r.pdf", "c.pdf")
    t = get_ticket(conn, a)
    assert (t["resume_id"], t["tailored_resume_path"], t["cover_letter_path"]) == (3, "r.pdf", "c.pdf")
