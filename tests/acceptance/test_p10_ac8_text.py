"""Phase 10 AC-8: supplied description text continues the pipeline for a blocked or new URL."""

from p10_helpers import Pipeline, failing_fetch, job_count, job_row, no_extract, ticket_of

URL = "https://example.com/careers/closed"
TEXT = "Staff Engineer\nYou will lead a small team building payment systems in Python and Go every day."


def fail_first(conn):
    from hireember.addjob import add_job_from_url

    first = add_job_from_url(conn, URL, fetch=failing_fetch("The page was not found (404)."), extract=no_extract)
    assert first.status == "failed"
    return first


def test_text_for_a_new_url_creates_the_job(conn):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, URL, text=TEXT, fetch=failing_fetch("must not fetch"), extract=no_extract)
    assert result.status == "added" and isinstance(result.ticket_id, int)
    row = job_row(conn, URL)
    assert row["strategy"] == "manual" and row["title"] == "Staff Engineer"
    assert "payment systems" in row["full_description"]


def test_text_reuses_the_blocked_job_and_resolves_the_queue(conn):
    from hireember import runs
    from hireember.addjob import add_job_from_url

    first = fail_first(conn)
    runs.enqueue_blocked(conn)
    result = add_job_from_url(conn, URL, text=TEXT, fetch=failing_fetch("must not fetch"), extract=no_extract)
    assert result.status == "added" and result.ticket_id == first.ticket_id
    assert job_count(conn) == 1
    assert "payment systems" in job_row(conn, URL)["full_description"]
    open_items = conn.execute("SELECT COUNT(*) FROM queue_items WHERE ticket_id = ? AND resolved_at IS NULL",
                              (first.ticket_id,)).fetchone()[0]
    assert open_items == 0


def test_run_with_text_goes_through_score_and_tailor(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    fail_first(conn)
    p = Pipeline(monkeypatch)
    rows = run_add_jobs(conn, [URL], text=TEXT, fetch=failing_fetch("must not fetch"), extract=no_extract)
    assert [r.status for r in rows] == ["added"]
    assert [c[0] for c in p.calls] == ["score", "tailor"]
    assert ticket_of(conn, URL)["status"] in ("pending", "blocked for human")
    assert rows[0].score == 8


def test_run_with_text_blocked_after_tailor_has_reason(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    Pipeline(monkeypatch, block_reason="no base resume")
    rows = run_add_jobs(conn, [URL], text=TEXT, fetch=failing_fetch("x"), extract=no_extract)
    assert rows[0].status == "added" and rows[0].next_step == "Blocked for human: no base resume"
    t = ticket_of(conn, URL)
    assert t["status"] == "blocked for human" and t["status_reason"] == "no base resume"
