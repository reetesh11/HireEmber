import pytest

from hireember import addjob
from hireember.addjob import AddRow, format_summary, load_state, next_step, save_state


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    yield c
    close_connection(isolated_db)


def test_next_step_texts():
    base = {"status": "pending", "status_reason": ""}
    assert next_step(None) == ""
    assert next_step(base) == addjob.STOPPED_NO_APPLY
    assert next_step(base, applying=True) == "Waiting at review"
    assert next_step({"status": "applied", "status_reason": ""}) == "Applied"
    assert next_step({"status": "pending", "status_reason": "limit: daily"}) == addjob.DAILY_LIMIT_STEP
    blocked = {"status": "blocked for human", "status_reason": "captcha"}
    assert next_step(blocked) == "Blocked for human: A CAPTCHA needs you to solve it."


def test_summary_counts():
    rows = [AddRow("u", "already added", 1, None, "", ""), AddRow("v", "failed", None, None, "", "")]
    assert format_summary(rows) == "2 URLs: 0 added, 1 already added, 1 failed."


def test_load_state_survives_bad_json(conn):
    from hireember import tickets

    tickets.set_setting(conn, addjob.STATE_KEY, "{not json")
    assert load_state(conn) == {"results": [], "progress": None}
    save_state(conn, running=False, rows=[], progress=None)
    assert load_state(conn)["results"] == []


def test_stage_exception_gives_failed_row(conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr("hireember.addjob.add_job_from_url", boom)
    rows = addjob.run_add_jobs(conn, ["https://a.example/1"])
    assert rows[0].status == "failed" and rows[0].reason == addjob.UNEXPECTED_REASON
