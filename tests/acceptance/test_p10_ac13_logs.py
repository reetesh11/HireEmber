"""Phase 10 AC-13: logs for added jobs hold no API keys and no page text at info level or above."""

import logging

from p10_helpers import DESC_MARK, Pipeline, job_page_for, simple_html

KEY = "sk-test-SECRET-KEY-98765"


def test_no_secret_or_page_text_in_info_logs(conn, monkeypatch, caplog):
    from hireember.addjob import run_add_jobs

    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(name, KEY)
    job_page_for(monkeypatch, {"https://example.com/jobs/1": simple_html(1)},
                 fail={"https://example.com/jobs/2": "The page was not found (404)."})
    Pipeline(monkeypatch)
    caplog.set_level(logging.INFO)
    run_add_jobs(conn, ["https://example.com/jobs/1", "https://example.com/jobs/2"], apply=True)
    logged = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.INFO)
    stored = "\n".join(str(tuple(r)) for r in conn.execute(
        "SELECT message FROM run_log WHERE level != 'debug'"))
    for blob in (logged, stored):
        assert KEY not in blob and DESC_MARK not in blob


def test_unexpected_error_details_stay_out_of_the_result(conn, monkeypatch):
    from hireember.addjob import add_job_from_url

    def boom(url):
        raise RuntimeError(f"{KEY} {DESC_MARK}")

    result = add_job_from_url(conn, "https://example.com/p", fetch=boom)
    assert KEY not in result.reason and DESC_MARK not in result.reason
