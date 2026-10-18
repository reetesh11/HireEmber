"""Phase 3 AC-9: a sign-in page blocks the ticket; after `queue ready` the run resumes on the same session."""

from typer.testing import CliRunner

import pytest

from p3_helpers import SESSION_LINK, add_ticket, agent_for, open_items, widen_cli_console, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _block_on_signin(conn, tmp, server, name="a1"):
    from hireember.apply.runner import apply_ticket

    tid = add_ticket(conn, tmp, name)
    agent, run = agent_for(server, "account_wall.html")
    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)
    return tid, outcome, run


def test_signin_page_blocks_with_account_needed_and_a_queue_entry(env, fixture_form_server):
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid, outcome, run = _block_on_signin(conn, tmp, fixture_form_server)

    assert outcome.result == "blocked" and outcome.reason == "account needed"
    assert run.filled == {} and run.submit_calls == 0
    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human" and ticket["status_reason"] == "account needed"
    [item] = open_items(conn, tid)
    assert item["kind"] == "account needed"
    assert item["company"] == "Acme"
    assert item["page_link"].endswith("/forms/account_wall.html")
    assert ticket["session_link"] == SESSION_LINK, "the browser is left open on the page"


def test_ready_returns_ticket_to_pending_and_the_run_resumes_on_the_same_page(env, fixture_form_server):
    from hireember.answers import ready_queue_item
    from hireember.apply.attempts import get_log
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_history, get_ticket

    conn, tmp = env
    tid, _, _ = _block_on_signin(conn, tmp, fixture_form_server)
    [item] = open_items(conn, tid)

    result = ready_queue_item(conn, item["id"])

    assert result.message == f"Ticket {tid} is ready to resume."
    assert get_ticket(conn, tid)["status"] == "pending"
    last = get_history(conn, tid)[-1]
    assert (last["status"], last["actor"], last["reason"]) == ("pending", "user", "ready")
    assert open_items(conn, tid) == []
    seen = {}

    def agent(session):
        seen["resume_from"] = session.resume_from
        seen["session_link"] = get_ticket(conn, tid)["session_link"]
        seen["status"] = get_ticket(conn, tid)["status"]
        session.closed("done for test")

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert seen["resume_from"] == item["page_link"]
    assert seen["session_link"] == SESSION_LINK
    assert seen["status"] == "applying"
    assert [r["detail"] for r in get_log(conn, tid) if r["kind"] == "resume"] == [item["page_link"]]


def test_live_session_link_is_on_the_ticket_while_the_run_is_active(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_history, get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "a2")
    seen = {}

    def agent(session):
        ticket = get_ticket(conn, tid)
        seen.update(status=ticket["status"], link=ticket["session_link"])
        session.closed("test")

    apply_ticket(conn, tid, agent, session_link="http://127.0.0.1:9444")

    assert seen == {"status": "applying", "link": "http://127.0.0.1:9444"}
    applying = [e for e in get_history(conn, tid) if e["status"] == "applying"]
    assert applying and applying[-1]["link"] == "http://127.0.0.1:9444"
    assert applying[-1]["link_kind"] == "session"


def test_answer_command_refuses_an_account_item_and_ready_refuses_a_question(env, fixture_form_server):
    import pytest

    from hireember.answers import QueueError, answer_queue_item, match_answer, ready_queue_item

    conn, tmp = env
    tid, _, _ = _block_on_signin(conn, tmp, fixture_form_server)
    [account] = open_items(conn, tid)
    other = add_ticket(conn, tmp, "a3", company="Other Co")
    question = match_answer(conn, other, "Do you like penguins?").queue_item_id

    with pytest.raises(QueueError) as exc:
        answer_queue_item(conn, account["id"], "whatever")
    assert str(exc.value) == 'Use "queue ready" for this item.'
    with pytest.raises(QueueError) as exc:
        ready_queue_item(conn, question)
    assert str(exc.value) == 'Use "queue answer" for this item.'
    with pytest.raises(QueueError) as exc:
        ready_queue_item(conn, 9999)
    assert str(exc.value) == "Queue item 9999 not found or already resolved."


def test_cli_queue_ready_and_list(env, fixture_form_server, monkeypatch):
    from hireember.cli import app
    from hireember.tickets import get_ticket

    conn, tmp = env
    widen_cli_console(monkeypatch)
    tid, _, _ = _block_on_signin(conn, tmp, fixture_form_server)
    [item] = open_items(conn, tid)

    listing = CliRunner().invoke(app, ["queue", "list"])
    assert listing.exit_code == 0, listing.output
    for text in ("Company", "Page", "account needed", "Acme", "account_wall.html"):
        assert text in listing.output

    ready = CliRunner().invoke(app, ["queue", "ready", str(item["id"])])
    assert ready.exit_code == 0, ready.output
    assert f"Ticket {tid} is ready to resume." in ready.output
    assert get_ticket(conn, tid)["status"] == "pending"

    again = CliRunner().invoke(app, ["queue", "ready", str(item["id"])])
    assert again.exit_code == 1
    assert f"Queue item {item['id']} not found or already resolved." in again.output


def test_ready_on_outcome_unknown_returns_the_ticket_to_pending(env):
    from hireember.answers import ready_queue_item
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "a4")

    def agent(session):
        session.submit_pressed()
        raise RuntimeError("killed")

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)
    [item] = open_items(conn, tid)
    assert item["kind"] == "outcome unknown"

    ready_queue_item(conn, item["id"])

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "pending" and ticket["status_reason"] == "ready"
    assert not ticket["submitted_at"]
