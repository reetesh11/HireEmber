"""Phase 3 AC-1: password field, CAPTCHA, unknown question and conflicting answers hand off to a human."""

import pytest

from p3_helpers import SESSION_LINK, COLOR_Q, add_ticket, agent_for, open_items, make_env

CASES = [
    ("password_field.html", "sensitive question", "Account password"),
    ("captcha.html", "captcha", None),
    ("unknown_question.html", "unknown question", "Why do you want to work with penguins?"),
    ("known_form.html", "conflicting answers", COLOR_Q),
]

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



@pytest.mark.parametrize("page,reason,empty_label", CASES, ids=[c[1] for c in CASES])
def test_gate_blocks_ticket_and_queues_item(env, fixture_form_server, page, reason, empty_label):
    from hireember.apply.runner import apply_ticket
    from hireember.answers import save_answer
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "g1")
    if reason == "conflicting answers":
        save_answer(conn, COLOR_Q, "Blue", replace=False)
        save_answer(conn, COLOR_Q, "Green", replace=False)
    agent, run = agent_for(fixture_form_server, page)

    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert outcome.result == "blocked"
    assert outcome.reason == reason
    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human"
    assert ticket["status_reason"] == reason
    items = open_items(conn, tid)
    assert [i["kind"] for i in items] == [reason]
    assert run.submit_calls == 0
    if empty_label:
        assert empty_label not in run.filled, "the gated field must stay empty"


def test_password_typed_field_never_gets_a_value(env):
    from hireember.apply.session import GateSession
    from hireember.tickets import get_ticket, set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "g2")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")
    session = GateSession(conn, tid)

    decision = session.answer_field("Create a passphrase", "password")

    assert decision.action == "stop" and decision.value is None
    assert decision.reason == "sensitive question"
    assert get_ticket(conn, tid)["status"] == "blocked for human"
    assert [i["kind"] for i in open_items(conn, tid)] == ["sensitive question"]
    assert decision.queue_item_id == open_items(conn, tid)[0]["id"]


def test_sensitive_question_text_is_blocked_even_for_a_text_field(env):
    from hireember.apply.session import GateSession
    from hireember.tickets import set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "g3")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")

    decision = GateSession(conn, tid).answer_field("Enter your social security number", "text")

    assert decision.action == "stop" and decision.value is None
    assert open_items(conn, tid)[0]["kind"] == "sensitive question"


def test_asking_the_same_unknown_question_twice_queues_it_once(env):
    from hireember.apply.session import GateSession
    from hireember.tickets import set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "g4")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")
    session = GateSession(conn, tid)

    first = session.answer_field("Describe your ideal day", "textarea")
    second = session.answer_field("Describe your ideal day", "textarea")

    assert first.action == second.action == "stop"
    assert len(open_items(conn, tid)) == 1
