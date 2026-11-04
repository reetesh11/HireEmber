"""Phase 10 AC-3 (unchanged behaviour): jobs that are not added by link are still location-skipped."""

import pytest

from p10_helpers import PROFILE_TORONTO


@pytest.fixture
def scoring(conn, tmp_path, monkeypatch):
    from p2_helpers import install_fake_llm, make_resume

    make_resume(conn, tmp_path, "Backend", "backend", "BASE RESUME TEXT")
    return lambda score: install_fake_llm(monkeypatch, score=score)


def test_non_manual_job_outside_location_is_still_skipped(conn, scoring):
    from hireember import gating
    from hireember.database import store_jobs

    scoring(9)
    url = "https://example.com/jobs/other"
    store_jobs(conn, [{"url": url, "title": "Python Dev", "location": "Austin, TX"}], "indeed", "jobspy")
    conn.execute("UPDATE jobs SET full_description = 'desc' WHERE url = ?", (url,))
    conn.commit()
    res = gating.score_job_for_ticket(conn, url, profile=PROFILE_TORONTO)
    assert res.status == "skipped" and res.reason == "location: Austin, TX"
