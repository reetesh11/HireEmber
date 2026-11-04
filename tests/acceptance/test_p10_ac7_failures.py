"""Phase 10 AC-7: unreadable pages give distinct plain reasons and a blocked ticket in the queue."""

import httpx
import pytest

from p10_helpers import (LOGIN_HTML, blank_extract, job_count, job_row, no_extract, public_resolver, static_fetch)

NOT_FOUND = "The page was not found (404)."
LOGIN = "The page needs you to sign in, so the description could not be read."


def transport_fetch(handler):
    from hireember.urlfetch import fetch_page

    return lambda url: fetch_page(url, transport=httpx.MockTransport(handler), resolver=public_resolver)


def open_queue(conn):
    from hireember import runs

    runs.enqueue_blocked(conn)
    return [dict(zip(r.keys(), tuple(r))) for r in conn.execute(
        "SELECT * FROM queue_items WHERE resolved_at IS NULL")]


def assert_blocked(conn, result, reason):
    from hireember import tickets

    assert result.status == "failed" and result.reason == reason
    assert isinstance(result.ticket_id, int)
    t = tickets.get_ticket(conn, result.ticket_id)
    assert t["status"] == "blocked for human" and t["status_reason"] == reason
    items = [i for i in open_queue(conn) if i["ticket_id"] == result.ticket_id]
    assert len(items) == 1 and items[0]["reason"] == reason
    row = job_row(conn, result.job_url)
    assert row["strategy"] == "manual" and row["detail_scraped_at"]


def test_404_fixture(conn):
    from hireember.addjob import add_job_from_url

    fetch = transport_fetch(lambda req: httpx.Response(404, text="nope"))
    assert_blocked(conn, add_job_from_url(conn, "https://example.com/gone", fetch=fetch, extract=no_extract),
                   NOT_FOUND)


def test_login_fixture(conn):
    from hireember.addjob import add_job_from_url

    fetch = transport_fetch(lambda req: httpx.Response(200, text=LOGIN_HTML))
    assert_blocked(conn, add_job_from_url(conn, "https://example.com/careers/9", fetch=fetch, extract=blank_extract),
                   LOGIN)


@pytest.mark.parametrize("status, reason", [(403, "The site blocked the request."),
                                            (429, "The site blocked the request."),
                                            (500, "The page could not be fetched.")])
def test_other_statuses(conn, status, reason):
    from hireember.addjob import add_job_from_url

    fetch = transport_fetch(lambda req: httpx.Response(status, text="x"))
    assert_blocked(conn, add_job_from_url(conn, "https://example.com/p", fetch=fetch, extract=no_extract), reason)


def test_timeout(conn):
    from hireember.addjob import add_job_from_url

    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    result = add_job_from_url(conn, "https://example.com/p", fetch=transport_fetch(handler), extract=no_extract)
    assert_blocked(conn, result, "The page did not load in time.")


def test_no_description(conn):
    from hireember.addjob import add_job_from_url

    html = "<html><body><h1>Hello</h1><p>Short.</p></body></html>"
    result = add_job_from_url(conn, "https://example.com/p", fetch=static_fetch(html), extract=blank_extract)
    assert_blocked(conn, result, "No job description was found on the page.")


def test_fetch_page_reasons_and_truncation():
    from hireember.urlfetch import FetchError, fetch_page

    ok = fetch_page("https://example.com/p", transport=httpx.MockTransport(
        lambda req: httpx.Response(200, text="<html>" + "a" * 5000 + "</html>")),
        resolver=public_resolver, max_bytes=1000)
    assert ok.status == 200 and ok.truncated is True and len(ok.html) <= 1000
    for status, reason in ((404, NOT_FOUND), (403, "The site blocked the request."),
                           (429, "The site blocked the request."), (503, "The page could not be fetched.")):
        with pytest.raises(FetchError) as exc:
            fetch_page("https://example.com/p", transport=httpx.MockTransport(
                lambda req, s=status: httpx.Response(s)), resolver=public_resolver)
        assert exc.value.reason == reason and exc.value.refused is False


def test_malformed_string_has_no_ticket(conn):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, "not a url", extract=no_extract)
    assert result.status == "failed" and result.reason == "That is not a valid web address."
    assert result.ticket_id is None and job_count(conn) == 0


def test_linkedin_is_refused_without_ticket(conn):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, "https://www.linkedin.com/jobs/view/123", extract=no_extract)
    assert result.status == "failed"
    assert result.reason == "LinkedIn links are not supported because they need a signed-in session."
    assert result.ticket_id is None and job_count(conn) == 0


def test_unexpected_error_is_plain(conn):
    from hireember.addjob import add_job_from_url

    def boom(url):
        raise RuntimeError("secret internals")

    result = add_job_from_url(conn, "https://example.com/p", fetch=boom, extract=no_extract)
    assert result.status == "failed" and result.reason == "Something went wrong adding this link."
