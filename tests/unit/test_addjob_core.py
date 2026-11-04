import pytest

from hireember import tickets
from hireember.addjob import add_job_from_url, normalize_url
from hireember.urlfetch import FetchResult

HTML = ("<html><body><h1>Engineer</h1><div class='job-description'><p>"
        "Build and run services for customers every day, with care and good tests.</p></div></body></html>")


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    yield c
    close_connection(isolated_db)


def fetch(url):
    return FetchResult(url=url, status=200, html=HTML, truncated=False)


def no_ai(url, text):
    raise AssertionError("no AI call expected")


def test_normalize_keeps_other_params_in_order():
    assert normalize_url("HTTPS://A.com/x/?b=1&utm_x=2&a=3#f") == "https://a.com/x?b=1&a=3"


def test_added_job_is_manual_with_pending_ticket(conn):
    res = add_job_from_url(conn, "https://a.example/j/1", fetch=fetch, extract=no_ai)
    assert res.status == "added"
    row = conn.execute("SELECT strategy, site FROM jobs WHERE url = ?", (res.job_url,)).fetchone()
    assert tuple(row) == ("manual", "a.example")
    t = tickets.get_ticket(conn, res.ticket_id)
    assert (t["status"], t["status_reason"]) == ("pending", "added by link")


def test_text_for_blocked_job_reuses_it(conn):
    from hireember.urlfetch import FetchError

    def bad(url):
        raise FetchError("The page was not found (404).")

    first = add_job_from_url(conn, "https://a.example/j/2", fetch=bad)
    again = add_job_from_url(conn, "https://a.example/j/2")
    assert again.status == "duplicate" and again.ticket_id == first.ticket_id
    done = add_job_from_url(conn, "https://a.example/j/2", text="Title\nA long enough description text here.")
    assert done.status == "added" and done.ticket_id == first.ticket_id
    assert tickets.get_ticket(conn, first.ticket_id)["status"] == "pending"
