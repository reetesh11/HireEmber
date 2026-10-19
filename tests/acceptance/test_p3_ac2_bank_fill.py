"""Phase 3 AC-2: after a queued question is answered, the next form is filled from the bank and logged."""

from typer.testing import CliRunner

import pytest

from p3_helpers import SESSION_LINK, COLOR_Q, add_ticket, agent_for, open_items, widen_cli_console, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _answer_first_ticket(conn, tmp, server):
    from hireember.apply.runner import apply_ticket
    from hireember.answers import answer_queue_item

    first = add_ticket(conn, tmp, "b1")
    agent, _ = agent_for(server, "known_form.html")
    outcome = apply_ticket(conn, first, agent, session_link=SESSION_LINK)
    assert outcome.result == "blocked" and outcome.reason == "unknown question"
    answer_queue_item(conn, open_items(conn, first)[0]["id"], "Blue")
    return first


def test_next_form_is_filled_from_bank_and_log_names_the_entry(env, fixture_form_server):
    from hireember.answers import list_answers
    from hireember.apply.attempts import get_log
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    _answer_first_ticket(conn, tmp, fixture_form_server)
    entry = list_answers(conn)[0]
    second = add_ticket(conn, tmp, "b2", company="Other Co")
    agent, run = agent_for(fixture_form_server, "known_form.html")

    outcome = apply_ticket(conn, second, agent, session_link=SESSION_LINK)

    assert outcome.result == "applied"
    assert run.filled[COLOR_Q] == "Blue"
    assert get_ticket(conn, second)["status"] == "applied"
    fills = [r for r in get_log(conn, second) if r["kind"] == "fill" and r["field"] == COLOR_Q]
    assert len(fills) == 1
    assert fills[0]["source"] == f"answer:{entry['id']}"
    assert list_answers(conn)[0]["times_used"] == 1


def test_profile_values_are_filled_and_logged_as_profile_source(env, fixture_form_server):
    from hireember.apply.attempts import get_log
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    _answer_first_ticket(conn, tmp, fixture_form_server)
    second = add_ticket(conn, tmp, "b3", company="Other Co")
    agent, run = agent_for(fixture_form_server, "known_form.html")

    apply_ticket(conn, second, agent, session_link=SESSION_LINK)

    assert run.filled["Full name"] == "Test Person"
    assert run.filled["Email"] == "test@example.com"
    sources = {r["field"]: r["source"] for r in get_log(conn, second) if r["kind"] == "fill"}
    assert sources["Full name"].startswith("profile:")
    assert sources["Email"].startswith("profile:")


def test_every_filled_field_in_the_log_has_a_source(env, fixture_form_server):
    from hireember.apply.attempts import get_log
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    _answer_first_ticket(conn, tmp, fixture_form_server)
    second = add_ticket(conn, tmp, "b4", company="Other Co")
    agent, _ = agent_for(fixture_form_server, "known_form.html")
    apply_ticket(conn, second, agent, session_link=SESSION_LINK)

    rows = get_log(conn, second)
    assert rows and all(set(r) >= {"id", "attempt", "time", "kind", "field", "source", "detail"} for r in rows)
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    fills = [r for r in rows if r["kind"] == "fill"]
    assert fills and all(r["source"] for r in fills)


def test_ticket_log_command_shows_the_source(env, fixture_form_server, monkeypatch):
    from hireember.answers import list_answers
    from hireember.apply.runner import apply_ticket
    from hireember.cli import app

    conn, tmp = env
    widen_cli_console(monkeypatch)
    _answer_first_ticket(conn, tmp, fixture_form_server)
    entry = list_answers(conn)[0]
    second = add_ticket(conn, tmp, "b5", company="Other Co")
    agent, _ = agent_for(fixture_form_server, "known_form.html")
    apply_ticket(conn, second, agent, session_link=SESSION_LINK)

    result = CliRunner().invoke(app, ["ticket", "log", str(second)])

    assert result.exit_code == 0, result.output
    assert f"answer:{entry['id']}" in result.output
    assert COLOR_Q in result.output


def test_ticket_log_command_handles_empty_and_unknown_tickets(env):
    from hireember.cli import app

    conn, tmp = env
    tid = add_ticket(conn, tmp, "b6")

    empty = CliRunner().invoke(app, ["ticket", "log", str(tid)])
    missing = CliRunner().invoke(app, ["ticket", "log", "9999"])

    assert empty.exit_code == 0
    assert f"No attempts logged for ticket {tid}." in empty.output
    assert missing.exit_code == 1
    assert "Ticket 9999 not found." in missing.output
