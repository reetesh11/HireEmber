"""Phase 10 AC-2, AC-15, AC-16: URL normalisation and duplicate detection."""

import pytest

from p10_helpers import (failing_fetch, job_count, make_ticket, no_extract, simple_html, static_fetch,
                         job_page_for, Pipeline)


@pytest.mark.parametrize("raw, expected", [
    ("https://Example.com/Jobs/1/?utm_source=x&gh_src=y&source=z&id=5&b=2&utm_medium=m#frag",
     "https://example.com/Jobs/1?id=5&b=2"),
    ("https://example.com/jobs/1/", "https://example.com/jobs/1"),
    ("https://example.com/jobs/1?b=2&a=1", "https://example.com/jobs/1?b=2&a=1"),
    ("https://example.com/jobs/1?utm_campaign=q&ref=keep", "https://example.com/jobs/1?ref=keep"),
    ("  not a url  ", "not a url"),
])
def test_normalize_url(raw, expected):
    from hireember.addjob import normalize_url

    assert normalize_url(raw) == expected


def test_same_job_with_other_tracking_is_duplicate(conn):
    from hireember.addjob import add_job_from_url

    fetch = static_fetch(simple_html(1))
    first = add_job_from_url(conn, "https://example.com/jobs/1?utm_source=a", fetch=fetch, extract=no_extract)
    second = add_job_from_url(conn, "https://EXAMPLE.com/jobs/1/?gh_src=b&source=c#x", fetch=failing_fetch("no"),
                              extract=no_extract)
    assert first.status == "added"
    assert second.status == "duplicate" and second.reason == "already added"
    assert second.ticket_id == first.ticket_id
    assert second.job_url == first.job_url == "https://example.com/jobs/1"
    assert job_count(conn) == 1


def test_application_url_match_is_duplicate(conn):
    from hireember.addjob import add_job_from_url
    from p1_helpers import add_job

    tid = add_job(conn, "https://jobs.example/orig", application_url="https://apply.example/y?utm_source=a")

    def boom(url):
        raise AssertionError("must not fetch a duplicate")

    result = add_job_from_url(conn, "https://apply.example/y/", fetch=boom, extract=no_extract)
    assert result.status == "duplicate" and result.reason == "already added" and result.ticket_id == tid
    assert job_count(conn) == 1


def test_stored_url_with_tracking_matches_after_normalisation(conn):
    from hireember.addjob import add_job_from_url
    from p1_helpers import add_job

    tid = add_job(conn, "https://jobs.example/z?utm_source=feed")
    result = add_job_from_url(conn, "https://jobs.example/z", fetch=failing_fetch("no"), extract=no_extract)
    assert (result.status, result.ticket_id) == ("duplicate", tid)


def test_job_with_applied_ticket_is_duplicate(conn):
    from hireember.addjob import add_job_from_url

    tid = make_ticket(conn, "done", status="applied")
    result = add_job_from_url(conn, "https://jobs.example/done?utm_medium=x", fetch=failing_fetch("no"),
                              extract=no_extract)
    assert result.status == "duplicate" and result.ticket_id == tid


def test_same_url_twice_in_one_run(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    rows = run_add_jobs(conn, ["https://example.com/jobs/1", "https://example.com/jobs/1?utm_source=a"])
    assert [r.status for r in rows] == ["added", "already added"]
    assert rows[1].ticket_id == rows[0].ticket_id
    assert rows[1].next_step == "Already in your tickets"
    assert job_count(conn) == 1
