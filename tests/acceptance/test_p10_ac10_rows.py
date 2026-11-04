"""Phase 10 AC-10 and the result rows: order, failures, score, next step, progress, summary, state."""

import json

from p10_helpers import Pipeline, job_page_for, simple_html, ticket_of

U1, U2, U3 = "https://example.com/jobs/1", "https://example.com/jobs/2", "https://example.com/jobs/3"


def three(conn, monkeypatch, **pipe):
    from hireember.addjob import run_add_jobs

    job_page_for(monkeypatch, {U1: simple_html(1), U3: simple_html(3)}, fail={U2: "The page was not found (404)."})
    p = Pipeline(monkeypatch, **pipe)
    progress = []
    rows = run_add_jobs(conn, [U1, U2, U3], progress=lambda d, t: progress.append((d, t)))
    return p, rows, progress


def test_one_failure_does_not_stop_the_others(conn, monkeypatch):
    p, rows, progress = three(conn, monkeypatch)
    assert [r.status for r in rows] == ["added", "failed", "added"]
    assert [r.url for r in rows] == [U1, U2, U3]
    assert all(isinstance(r.ticket_id, int) for r in rows)
    assert [r.score for r in rows] == [8, None, 8]
    assert rows[0].next_step == "Stopped at ticket (run with --apply to apply)"
    assert rows[1].next_step == "Blocked for human: The page was not found (404)."
    assert ticket_of(conn, U2)["status"] == "blocked for human"
    assert progress == [(1, 3), (2, 3), (3, 3)]


def test_score_then_tailor_per_added_job(conn, monkeypatch):
    p, rows, _ = three(conn, monkeypatch)
    names = [c[0] for c in p.calls]
    assert names == ["score", "tailor", "score", "tailor"]
    assert [c[1] for c in p.calls if c[0] == "score"] == [U1, U3]


def test_no_launcher_without_apply(conn, monkeypatch):
    p, rows, _ = three(conn, monkeypatch)
    assert p.launches == [] and ("preflight", "apply") not in p.calls


def test_failed_row_without_ticket_has_reason_only(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    rows = run_add_jobs(conn, ["ftp://example.com/x", "not a url"])
    assert [r.status for r in rows] == ["failed", "failed"]
    assert rows[0].ticket_id is None and rows[0].next_step == "Only http and https links are supported."
    assert rows[1].next_step == "That is not a valid web address."


def test_unexpected_error_in_a_stage_is_a_failed_row(conn, monkeypatch):
    from hireember.addjob import run_add_jobs

    Pipeline(monkeypatch)

    def boom(*a, **k):
        raise RuntimeError("page fetcher exploded")

    monkeypatch.setattr("hireember.addjob.fetch_page", boom)
    rows = run_add_jobs(conn, [U1, U2])
    assert len(rows) == 2 and all(r.status == "failed" for r in rows)
    assert all(r.reason == "Something went wrong adding this link." for r in rows)


def test_format_summary():
    from hireember.addjob import AddRow, format_summary

    def row(status):
        return AddRow(url="u", status=status, ticket_id=1, score=None, reason="", next_step="")

    rows = [row("added"), row("failed"), row("added")]
    assert format_summary(rows) == "3 URLs: 2 added, 0 already added, 1 failed."
    assert format_summary([row("already added")]) == "1 URLs: 0 added, 1 already added, 0 failed."


def test_state_round_trip(conn):
    from hireember.addjob import AddRow, load_state, save_state

    assert load_state(conn)["results"] == []
    rows = [AddRow(url=U1, status="added", ticket_id=4, score=8, reason="", next_step="Waiting at review"),
            AddRow(url=U2, status="failed", ticket_id=None, score=None, reason="r", next_step="r")]
    save_state(conn, running=True, rows=rows, progress={"done": 2, "total": 3})
    state = load_state(conn)
    assert state["progress"] == {"done": 2, "total": 3}
    assert state["results"][0] == {"url": U1, "status": "added", "ticket_id": 4, "score": 8, "reason": "",
                                   "next_step": "Waiting at review"}
    assert [r["status"] for r in state["results"]] == ["added", "failed"]
    raw = conn.execute("SELECT value FROM settings WHERE key = 'add_jobs_state'").fetchone()[0]
    assert json.loads(raw)
    save_state(conn, running=False, rows=rows, progress=None)
    assert load_state(conn)["progress"] is None
