"""Phase 10 AC-3: manual jobs bypass the phase 9 filters; manual low scores stay at the ticket."""

import pytest

from p10_helpers import (PROFILE_TORONTO, Pipeline, job_page_for, job_row, no_extract, static_fetch, ticket_of)


def forbid_filters(monkeypatch):
    from hireember import intake

    def boom(*a, **k):
        raise AssertionError("the phase 9 filters must not run for a job added by link")

    monkeypatch.setattr(intake.JobFilter, "reason", boom)
    monkeypatch.setattr(intake.JobFilter, "load", classmethod(lambda cls, *a, **k: boom()))
    monkeypatch.setattr(intake, "store_filtered", boom)
    monkeypatch.setattr(intake, "mark_dropped", boom)


SALES_HTML = ("<html><body><h1>Sales Manager</h1><div class='job-description'>"
              "<p>Sell our product to enterprise customers across Antarctica every single quarter.</p>"
              "</div></body></html>")


def test_add_stores_manual_job_without_filters(conn, monkeypatch):
    from hireember.addjob import add_job_from_url

    forbid_filters(monkeypatch)
    result = add_job_from_url(conn, "https://example.com/jobs/sales", fetch=static_fetch(SALES_HTML),
                              extract=no_extract)
    assert result.status == "added"
    row = job_row(conn, result.job_url)
    assert row["strategy"] == "manual" and row["title"] == "Sales Manager"
    t = ticket_of(conn, result.job_url)
    assert t["status"] != "skipped"
    assert t["status"] == "pending" and t["status_reason"] == "added by link"
    assert t["score"] is None


def test_run_keeps_excluded_title_and_shows_low_score(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    forbid_filters(monkeypatch)
    job_page_for(monkeypatch, default_html=SALES_HTML)
    Pipeline(monkeypatch, score=2)
    rows = run_add_jobs(conn, ["https://example.com/jobs/sales"])
    assert rows[0].status == "added" and rows[0].score == 2
    assert ticket_of(conn, "https://example.com/jobs/sales")["status"] != "skipped"


def _manual_job(conn, location="Austin, TX"):
    from hireember import tickets
    from hireember.database import store_jobs

    url = "https://example.com/jobs/m1"
    store_jobs(conn, [{"url": url, "title": "Python Dev", "location": location}], "example.com", "manual")
    conn.execute("UPDATE jobs SET full_description = 'Write Python services.' WHERE url = ?", (url,))
    conn.commit()
    tickets.open_ticket(conn, url, "pending", "added by link")
    return url


@pytest.fixture
def scoring(conn, tmp_path, monkeypatch):
    from p2_helpers import install_fake_llm, make_resume

    make_resume(conn, tmp_path, "Backend", "backend", "BASE RESUME TEXT")
    return lambda score: install_fake_llm(monkeypatch, score=score)


def test_manual_job_is_not_location_skipped_and_low_score_stays_pending(conn, scoring):
    from hireember import gating

    scoring(5)
    url = _manual_job(conn)
    res = gating.score_job_for_ticket(conn, url, profile=PROFILE_TORONTO)
    t = ticket_of(conn, url)
    assert t["status"] == "pending"
    assert t["status_reason"] == "score 5 below threshold 7 (added by link)"
    assert t["score"] == 5 and res.score == 5


def test_manual_job_high_score_stays_pending(conn, scoring):
    from hireember import gating

    scoring(9)
    url = _manual_job(conn)
    gating.score_job_for_ticket(conn, url, profile=PROFILE_TORONTO)
    t = ticket_of(conn, url)
    assert t["status"] == "pending" and t["score"] == 9
