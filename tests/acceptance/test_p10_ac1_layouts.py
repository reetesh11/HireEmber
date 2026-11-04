"""Phase 10 AC-1: add_job_from_url fills title, company, location and description for each layout."""

import pytest

from p10_helpers import (ASHBY_HTML, DESC_MARK, GREENHOUSE_HTML, JSON_LD_HTML, LEVER_HTML, UNKNOWN_EXTRACT,
                         UNKNOWN_HTML, WORKDAY_HTML, blank_extract, job_row, no_extract,
                         static_fetch)

CASES = [
    ("jsonld", "https://careers.acme.example/jobs/1", JSON_LD_HTML, "Backend Engineer", "Acme Corp", "Berlin"),
    ("greenhouse", "https://boards.greenhouse.io/acme/jobs/123", GREENHOUSE_HTML, "Data Engineer", None,
     "Remote"),
    ("lever", "https://jobs.lever.co/acme/2", LEVER_HTML, "Product Designer", None, "Lisbon"),
    ("ashby", "https://jobs.ashbyhq.com/acme/3", ASHBY_HTML, "Site Reliability Engineer", None, "Toronto"),
    ("workday", "https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Dublin/Analyst_R1", WORKDAY_HTML,
     "Business Analyst", None, "Dublin"),
]


@pytest.mark.parametrize("name, url, html, title, company, location", CASES, ids=[c[0] for c in CASES])
def test_known_layouts_use_the_cascade_not_the_ai(conn, name, url, html, title, company, location):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, url, fetch=static_fetch(html), extract=no_extract)
    assert result.status == "added", result
    assert isinstance(result.ticket_id, int)
    assert result.reason == ""
    row = job_row(conn, result.job_url)
    assert row["title"] == title
    assert row["company_name"] and (company is None or row["company_name"] == company)
    assert location in (row["location"] or "")
    assert DESC_MARK in (row["full_description"] or "")
    assert row["detail_scraped_at"]


def test_unknown_layout_calls_the_extractor_once(conn):
    from hireember.addjob import add_job_from_url

    calls = []

    def extract(url, text):
        calls.append((url, text))
        return dict(UNKNOWN_EXTRACT)

    result = add_job_from_url(conn, "https://example.com/careers/chef", fetch=static_fetch(UNKNOWN_HTML),
                              extract=extract)
    assert result.status == "added", result
    assert len(calls) == 1
    row = job_row(conn, result.job_url)
    assert (row["title"], row["company_name"], row["location"]) == ("Chef de Cuisine", "Petit Bistro", "Paris")
    assert DESC_MARK in row["full_description"]


def test_parse_job_page_returns_none_without_description():
    from hireember.enrichment.page import parse_job_page

    assert parse_job_page(UNKNOWN_HTML, "https://example.com/x", extract=blank_extract) is None


def test_parse_job_page_jsonld_keys():
    from hireember.enrichment.page import parse_job_page

    data = parse_job_page(JSON_LD_HTML, "https://careers.acme.example/jobs/1", extract=no_extract)
    assert data["title"] == "Backend Engineer" and data["company"] == "Acme Corp"
    assert set(data) >= {"title", "company", "location", "description", "application_url"}


def test_looks_like_login_detects_password_form():
    from hireember.enrichment.page import looks_like_login
    from p10_helpers import LOGIN_HTML

    assert looks_like_login(LOGIN_HTML, "https://example.com/careers/9") is True
    assert looks_like_login(GREENHOUSE_HTML, "https://boards.greenhouse.io/acme/jobs/123") is False
