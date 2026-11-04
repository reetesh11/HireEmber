"""Phase 10 AC-4, AC-5, AC-11 at the run level: launcher calls, preflight, review, limits, next steps."""

from datetime import datetime, timezone

from p10_helpers import Pipeline, job_page_for, make_ticket, simple_html

U = [f"https://example.com/jobs/{i}" for i in range(1, 5)]


def setup(conn, monkeypatch, urls=U, **pipe):
    job_page_for(monkeypatch, default_html=simple_html(1), fail={})
    return Pipeline(monkeypatch, **pipe)


def test_launcher_called_for_added_jobs_only_in_order(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    p = setup(conn, monkeypatch)
    dup = make_ticket(conn, "dup", status="pending")  # noqa: F841
    other = make_ticket(conn, "other", status="pending")  # noqa: F841
    job_page_for(monkeypatch, {U[0]: simple_html(1), U[2]: simple_html(3)}, fail={U[1]: "The page was not found (404)."})
    rows = run_add_jobs(conn, [U[0], U[1], "https://jobs.example/dup", U[2]], apply=True)
    assert [r.status for r in rows] == ["added", "failed", "already added", "added"]
    assert p.launched_urls == [U[0], U[2]]
    assert p.calls.index(("preflight", "apply")) < p.calls.index(("launch", U[0]))
    assert [c for c in p.calls if c[0] == "preflight"] == [("preflight", "apply")]


def test_launcher_arguments_and_review_default(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    p = setup(conn, monkeypatch)
    run_add_jobs(conn, [U[0]], apply=True)
    kw = p.launches[0]
    assert kw["limit"] == 1 and kw["target_url"] == U[0] and kw["headless"] is False and kw["review"] is True


def test_review_false_is_passed_explicitly(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    p = setup(conn, monkeypatch)
    run_add_jobs(conn, [U[0]], apply=True, review=False)
    assert p.launches[0]["review"] is False


def test_preflight_failure_applies_to_nothing(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    p = setup(conn, monkeypatch, preflight_ok=False)
    rows = run_add_jobs(conn, U[:2], apply=True)
    assert p.launches == []
    assert [r.status for r in rows] == ["added", "added"]
    assert all(r.next_step.startswith("Stopped at ticket: ") for r in rows)


def test_nothing_added_skips_apply(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    p = setup(conn, monkeypatch)
    rows = run_add_jobs(conn, ["ftp://x.example/a"], apply=True)
    assert rows[0].status == "failed" and p.launches == []


def test_next_step_from_ticket_state(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    outcomes = {U[0]: ("applied", ""), U[1]: ("blocked for human", "captcha"),
                U[2]: ("blocked for human", "account needed"), U[3]: ("pending", "")}
    p = setup(conn, monkeypatch, outcomes=outcomes)
    rows = run_add_jobs(conn, U, apply=True)
    assert [r.next_step for r in rows] == [
        "Applied", "Blocked for human: A CAPTCHA needs you to solve it.",
        "Blocked for human: A sign-in is needed to continue.", "Waiting at review"]
    assert p.launched_urls == U


def test_unsupported_reason_is_used_as_is(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    setup(conn, monkeypatch, outcomes={U[0]: ("blocked for human", "unsupported ATS flow")})
    rows = run_add_jobs(conn, [U[0]], apply=True)
    assert rows[0].next_step == "Blocked for human: unsupported ATS flow"


def test_daily_limit_from_setting(conn, monkeypatch):
    from hireember import tickets
    from hireember.addjob import run_add_jobs

    tickets.set_setting(conn, "schedule_apply_limit", "2")
    p = setup(conn, monkeypatch)
    rows = run_add_jobs(conn, U[:3], apply=True)
    assert p.launched_urls == U[:2]
    assert rows[2].status == "added" and rows[2].next_step == "Daily apply limit reached; will wait."


def test_daily_limit_counts_jobs_applied_today(conn, monkeypatch):
    from hireember import tickets
    from hireember.addjob import run_add_jobs

    tickets.set_setting(conn, "schedule_apply_limit", "2")
    make_ticket(conn, "earlier", status="applied", submitted_at=datetime.now(timezone.utc).isoformat())
    p = setup(conn, monkeypatch)
    rows = run_add_jobs(conn, U[:2], apply=True)
    assert p.launched_urls == [U[0]]
    assert rows[1].next_step == "Daily apply limit reached; will wait."


def test_pending_with_daily_limit_reason(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    setup(conn, monkeypatch, outcomes={U[0]: ("pending", "limit: daily")})
    rows = run_add_jobs(conn, [U[0]], apply=True)
    assert rows[0].next_step == "Daily apply limit reached; will wait."
