"""AC-4: discovery never stores a job whose URL or application URL is on LinkedIn."""

import pandas as pd

INDEED_URL = "https://www.indeed.com/viewjob?jk=1"


def _stored_urls(conn) -> list[str]:
    return sorted(r[0] for r in conn.execute("SELECT url FROM jobs").fetchall())


def test_linkedin_url_detection_uses_host():
    from applypilot.config import is_linkedin_url

    for url in (
        "https://www.linkedin.com/jobs/view/123",
        "https://linkedin.com/jobs/view/456",
        "https://uk.LinkedIn.com/jobs/view/7",
        "www.linkedin.com/jobs/view/1",
    ):
        assert is_linkedin_url(url) is True, url
    for url in (
        None,
        "",
        "nan",
        INDEED_URL,
        "https://notlinkedin.com/x",
        "https://example.com/?ref=linkedin.com",
    ):
        assert is_linkedin_url(url) is False, url


def test_store_jobspy_results_skips_linkedin_job_urls(tmp_path):
    from applypilot.database import init_db
    from applypilot.discovery.jobspy import store_jobspy_results

    conn = init_db(tmp_path / "t.db")
    df = pd.DataFrame(
        [
            {"job_url": "https://www.linkedin.com/jobs/view/123", "title": "A", "company": "X", "site": "linkedin"},
            {"job_url": "https://linkedin.com/jobs/view/456", "title": "B", "company": "Y", "site": "linkedin"},
            {"job_url": INDEED_URL, "title": "C", "company": "Z", "site": "indeed"},
        ]
    )

    assert store_jobspy_results(conn, df, "python developer") == (1, 0)
    assert _stored_urls(conn) == [INDEED_URL]


def test_store_jobspy_results_skips_linkedin_direct_apply_url(tmp_path):
    from applypilot.database import init_db
    from applypilot.discovery.jobspy import store_jobspy_results

    conn = init_db(tmp_path / "t.db")
    other = "https://www.indeed.com/viewjob?jk=2"
    df = pd.DataFrame(
        [
            {"job_url": other, "job_url_direct": "https://www.linkedin.com/jobs/view/999", "title": "A"},
            {"job_url": INDEED_URL, "job_url_direct": "https://boards.greenhouse.io/acme/jobs/1", "title": "B"},
        ]
    )

    assert store_jobspy_results(conn, df, "python developer") == (1, 0)
    assert _stored_urls(conn) == [INDEED_URL]


def test_store_jobs_skips_linkedin_url_and_application_url(tmp_path):
    from applypilot.database import init_db, store_jobs

    conn = init_db(tmp_path / "t.db")
    jobs = [
        {"url": "https://www.linkedin.com/jobs/view/123", "title": "A"},
        {"url": "https://example.com/careers/1", "application_url": "https://linkedin.com/jobs/view/456", "title": "B"},
        {"url": INDEED_URL, "title": "C"},
    ]

    assert store_jobs(conn, jobs, site="TestSite", strategy="json_ld") == (1, 0)
    assert _stored_urls(conn) == [INDEED_URL]


def test_workday_store_results_skips_linkedin_url(tmp_path):
    from applypilot.database import init_db
    from applypilot.discovery.workday import store_results

    conn = init_db(tmp_path / "t.db")
    good = "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_R1"
    jobs = [
        {"apply_url": "https://www.linkedin.com/jobs/view/321", "title": "A", "employer_name": "Acme"},
        {"apply_url": good, "title": "B", "employer_name": "Acme"},
    ]

    assert store_results(conn, jobs, employers={}) == (1, 0)
    assert _stored_urls(conn) == [good]
