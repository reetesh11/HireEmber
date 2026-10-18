import json

import pytest

import hireember.config as config
from hireember.answers import list_queue, ready_queue_item
from hireember.apply.runner import apply_ticket, recover_stale_tickets
from hireember.apply.session import GateSession
from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import get_ticket, set_company_manual, set_job_score, set_status


@pytest.fixture
def env(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"personal": {"full_name": "Test Person"}}))
    monkeypatch.setattr(config, "PROFILE_PATH", profile)
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    yield conn
    close_connection(db)


def add(conn, n, company="Acme", title=None):
    store_jobs(conn, [{"url": f"u{n}", "title": title or f"T{n}", "company": company,
                       "location": f"L{n}"}], "S", "t")
    return set_job_score(conn, f"u{n}", 8)


def never(session):
    raise AssertionError("agent must not be called")


def test_duplicate_and_manual_never_call_the_agent(env):
    first = add(env, 1, title="Same")
    second = add(env, 2, title="Same")
    env.execute("UPDATE jobs SET location_normalized = 'x', title_normalized = 'same'")
    env.commit()
    set_status(env, first, "started")
    assert apply_ticket(env, second, never).result == "duplicate"
    other = add(env, 3, company="Manual Co")
    set_company_manual(env, "manual co")
    out = apply_ticket(env, other, never)
    assert out.result == "blocked" and out.reason == "manual site"
    assert [i["kind"] for i in list_queue(env) if i["ticket_id"] == other] == ["manual site"]
    assert apply_ticket(env, other, never).result == "skipped"


def test_exception_before_and_after_submit(env):
    a, b = add(env, 1, "A"), add(env, 2, "B")

    def before(session):
        raise RuntimeError("boom")

    def after(session):
        session.submit_pressed()
        raise RuntimeError("boom")

    assert apply_ticket(env, a, before).result == "interrupted"
    t = get_ticket(env, a)
    assert (t["status"], t["status_reason"]) == ("pending", "interrupted before submit")
    assert apply_ticket(env, b, after).reason == "outcome unknown"
    assert get_ticket(env, b)["status"] == "blocked for human"


def test_agent_finishing_without_result(env):
    a = add(env, 1)
    out = apply_ticket(env, a, lambda s: None)
    assert out.result == "interrupted" and out.reason == "agent finished without a result"


def test_recover_stale(env):
    a, b = add(env, 1, "A"), add(env, 2, "B")
    for t in (a, b):
        set_status(env, t, "started")
        set_status(env, t, "applying")
    GateSession(env, b).submit_pressed()
    assert recover_stale_tickets(env) == [a, b]
    assert get_ticket(env, a)["status"] == "pending"
    assert get_ticket(env, b)["status_reason"] == "outcome unknown"
    assert recover_stale_tickets(env) == []


def test_queue_ready_then_apply_exposes_resume_from(env):
    a = add(env, 1)

    def stop(session):
        session.stop("account needed", "http://page")

    apply_ticket(env, a, stop)
    ready_queue_item(env, list_queue(env)[0]["id"])
    seen = {}

    def agent(session):
        seen["from"] = session.resume_from
        session.closed("done")

    apply_ticket(env, a, agent)
    assert seen["from"] == "http://page"
