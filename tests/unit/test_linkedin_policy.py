"""Unit tests for the LinkedIn policy helpers and discovery filtering."""

import logging

import pytest

from applypilot import config


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/1",
        "https://linkedin.com/jobs/view/2",
        "https://uk.linkedin.com/jobs/view/3",
        "linkedin.com/jobs/view/4",
        "www.linkedin.com/jobs/view/5",
        "HTTPS://WWW.LINKEDIN.COM/JOBS/VIEW/6",
    ],
)
def test_is_linkedin_url_true(url):
    assert config.is_linkedin_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "nan",
        "https://notlinkedin.com/x",
        "https://example.com/?ref=linkedin.com",
        "https://www.indeed.com/viewjob?jk=1",
        "https://linkedin.com.evil.example/jobs",
    ],
)
def test_is_linkedin_url_false(url):
    assert config.is_linkedin_url(url) is False


def test_resolve_jobspy_sites_defaults():
    assert config.resolve_jobspy_sites(None) == ["indeed", "zip_recruiter"]


def test_resolve_jobspy_sites_drops_linkedin_with_warning(caplog):
    caplog.set_level(logging.WARNING, logger="applypilot.config")
    assert config.resolve_jobspy_sites(["LinkedIn", "indeed"]) == ["indeed"]
    assert any("LinkedIn" in r.getMessage() for r in caplog.records)


def test_resolve_jobspy_sites_can_be_empty():
    assert config.resolve_jobspy_sites(["linkedin"]) == []


def test_resolve_jobspy_sites_keeps_order_without_warning(caplog):
    caplog.set_level(logging.WARNING, logger="applypilot.config")
    assert config.resolve_jobspy_sites(["zip_recruiter", "glassdoor"]) == ["zip_recruiter", "glassdoor"]
    assert not caplog.records


def test_linkedin_blocked_error_message():
    err = config.LinkedInBlockedError("https://www.linkedin.com/jobs/view/1")
    assert isinstance(err, ValueError)
    assert "LinkedIn" in str(err)
    assert "https://www.linkedin.com/jobs/view/1" in str(err)


def _urls(conn):
    return sorted(r[0] for r in conn.execute("SELECT url FROM jobs"))


def test_database_store_jobs_skips_linkedin(tmp_path):
    from applypilot.database import init_db, store_jobs

    conn = init_db(tmp_path / "t.db")
    jobs = [
        {"url": "https://uk.linkedin.com/jobs/view/1"},
        {"url": "https://acme.example/jobs/2", "application_url": "linkedin.com/jobs/view/2"},
        {"url": "https://acme.example/jobs/3"},
    ]
    assert store_jobs(conn, jobs, site="Acme", strategy="json_ld") == (1, 0)
    assert store_jobs(conn, jobs, site="Acme", strategy="json_ld") == (0, 1)
    assert _urls(conn) == ["https://acme.example/jobs/3"]


def test_workday_store_results_skips_linkedin(tmp_path):
    from applypilot.database import init_db
    from applypilot.discovery.workday import store_results

    conn = init_db(tmp_path / "t.db")
    jobs = [
        {"apply_url": "https://linkedin.com/jobs/view/9", "title": "A"},
        {"apply_url": "https://acme.wd1.myworkdayjobs.com/x/job/1", "title": "B"},
    ]
    assert store_results(conn, jobs, employers={}) == (1, 0)
    assert _urls(conn) == ["https://acme.wd1.myworkdayjobs.com/x/job/1"]


def test_search_jobs_with_only_linkedin_does_not_scrape(monkeypatch):
    import applypilot.discovery.jobspy as jobspy_mod

    def fail(**kwargs):
        raise AssertionError("scrape_jobs must not be called")

    monkeypatch.setattr(jobspy_mod, "scrape_jobs", fail)
    result = jobspy_mod.search_jobs("python", "Remote", sites=["linkedin"])
    assert result == {"error": "no JobSpy sites configured", "total": 0, "new": 0, "existing": 0}
