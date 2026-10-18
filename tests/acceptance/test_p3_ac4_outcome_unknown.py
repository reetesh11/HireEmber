"""Phase 3 AC-4: a run stopped after submit is never retried; stale applying tickets are recovered."""

import pytest

from p3_helpers import SESSION_LINK, add_ticket, open_items, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _acquirable_urls(conn):
    from hireember.apply import launcher

    urls = []
    while True:
        job = launcher.acquire_job(min_score=1)
        if job is None:
            return urls
        urls.append(job["url"])


def test_run_killed_after_submit_blocks_with_outcome_unknown(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o1")

    def agent(session):
        session.submit_pressed()
        raise RuntimeError("process killed")

    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human"
    assert ticket["status_reason"] == "outcome unknown"
    assert outcome.result == "blocked" and outcome.reason == "outcome unknown"
    assert [i["kind"] for i in open_items(conn, tid)] == ["outcome unknown"]


def test_keyboard_interrupt_after_submit_is_reraised_and_still_blocks(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o2")

    def agent(session):
        session.submit_pressed()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert get_ticket(conn, tid)["status_reason"] == "outcome unknown"
    assert get_ticket(conn, tid)["status"] == "blocked for human"


def test_outcome_unknown_ticket_is_never_picked_up_again(env):
    from hireember.apply.limits import eligible_ticket_ids
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o3")

    def agent(session):
        session.submit_pressed()
        raise RuntimeError("process killed")

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert tid not in eligible_ticket_ids(conn)
    assert "https://jobs.example/o3" not in _acquirable_urls(conn)
    again = apply_ticket(conn, tid, lambda s: pytest.fail("agent must not be called"),
                         session_link=SESSION_LINK)
    assert again.result == "skipped"


def test_run_interrupted_before_submit_returns_to_pending(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o4")

    def agent(session):
        raise RuntimeError("browser crashed")

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "pending"
    assert ticket["status_reason"] == "interrupted before submit"
    assert open_items(conn, tid) == []


def test_stale_applying_ticket_without_submit_goes_back_to_pending(env):
    from hireember.apply.runner import recover_stale_tickets
    from hireember.tickets import get_history, get_ticket, set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o5")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")

    assert recover_stale_tickets(conn) == [tid]

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "pending"
    assert ticket["status_reason"] == "recovered after interrupted run"
    last = get_history(conn, tid)[-1]
    assert (last["status"], last["actor"], last["reason"]) == (
        "pending", "system", "recovered after interrupted run")


def test_stale_applying_ticket_after_submit_is_blocked_outcome_unknown(env):
    from hireember.apply.runner import recover_stale_tickets
    from hireember.apply.session import GateSession
    from hireember.tickets import get_ticket, set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o6")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")
    GateSession(conn, tid).submit_pressed()

    assert recover_stale_tickets(conn) == [tid]

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human"
    assert ticket["status_reason"] == "outcome unknown"
    assert [i["kind"] for i in open_items(conn, tid)] == ["outcome unknown"]


def test_recovery_leaves_other_tickets_alone(env):
    from hireember.apply.runner import recover_stale_tickets
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "o7")

    assert recover_stale_tickets(conn) == []
    assert get_ticket(conn, tid)["status"] == "pending"
