import pytest

from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import (
    InvalidStatusError,
    TicketError,
    TicketNotFoundError,
    ensure_ticket,
    get_history,
    get_or_create_company,
    get_ticket,
    get_ticket_by_url,
    get_threshold,
    set_job_company,
    set_job_score,
    set_setting,
    set_status,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    store_jobs(c, [{"url": "u1", "title": "T", "company": "Acme"}], "S", "t")
    yield c
    close_connection(db)


def test_company_lookup_is_case_insensitive(conn):
    a = get_or_create_company(conn, "Globex")
    assert get_or_create_company(conn, "  GLOBEX ") == a
    assert set_job_company(conn, "u1", "globex") == a
    assert conn.execute("SELECT company_id FROM jobs WHERE url='u1'").fetchone()[0] == a


def test_threshold_default_and_setting(conn):
    assert get_threshold(conn) == 7
    set_setting(conn, "score_threshold", "9")
    set_setting(conn, "score_threshold", " 8 ")
    assert get_threshold(conn) == 8


def test_set_job_score_creates_ticket_and_keeps_status_on_rescore(conn):
    tid = set_job_score(conn, "u1", 9, "great")
    t = get_ticket(conn, tid)
    assert (t["status"], t["score"], t["score_reason"]) == ("pending", 9, "great")
    set_status(conn, tid, "started")
    assert set_job_score(conn, "u1", 1, "bad") == tid
    assert get_ticket(conn, tid)["status"] == "started"
    assert get_ticket_by_url(conn, "nope") is None


def test_ensure_ticket_requires_scored_job(conn):
    with pytest.raises(TicketError):
        ensure_ticket(conn, "u1")
    with pytest.raises(TicketError):
        ensure_ticket(conn, "missing")
    conn.execute("UPDATE jobs SET fit_score = 3 WHERE url='u1'")
    tid = ensure_ticket(conn, "u1")
    assert get_ticket(conn, tid)["status"] == "skipped"


def test_set_status_validation_and_history(conn):
    tid = set_job_score(conn, "u1", 9)
    with pytest.raises(InvalidStatusError):
        set_status(conn, tid, "nope")
    with pytest.raises(ValueError):
        set_status(conn, tid, "closed", actor="robot")
    with pytest.raises(TicketNotFoundError):
        get_ticket(conn, 999)
    set_status(conn, tid, "pending")
    set_status(conn, tid, "closed", actor="user", reason="r", link="x", link_kind="k")
    h = get_history(conn, tid)
    assert [e["status"] for e in h] == ["pending", "closed"]
    assert (h[1]["actor"], h[1]["link"], h[1]["link_kind"]) == ("user", "x", "k")


def test_commit_false_batches(conn):
    set_job_score(conn, "u1", 9, commit=False)
    conn.rollback()
    assert get_ticket_by_url(conn, "u1") is None
