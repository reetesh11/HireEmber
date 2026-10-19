"""Phase 3 AC-7: every applied ticket has a confirmation link or the unverified flag."""

import pytest

from p3_helpers import SESSION_LINK, add_ticket, agent_for, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def test_submit_with_confirmation_link_stores_it(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "c1")
    agent, run = agent_for(fixture_form_server, "upload_form.html", confirmation="https://acme.example/thanks/1")

    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    ticket = get_ticket(conn, tid)
    assert outcome.result == "applied"
    assert ticket["status"] == "applied"
    assert ticket["confirmation_link"] == "https://acme.example/thanks/1"
    assert not ticket["unverified"]
    assert ticket["submitted_at"]
    assert not ticket["session_link"]


def test_submit_without_confirmation_is_marked_unverified(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "c2")
    agent, _ = agent_for(fixture_form_server, "upload_form.html", confirmation=None)

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "applied"
    assert ticket["unverified"] == 1
    assert not ticket["confirmation_link"]


def test_blank_confirmation_counts_as_unverified(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "c3")
    agent, _ = agent_for(fixture_form_server, "upload_form.html", confirmation="   ")

    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert get_ticket(conn, tid)["unverified"] == 1


def test_no_applied_ticket_lacks_both(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    for i, link in enumerate(["https://acme.example/ok", None, ""]):
        tid = add_ticket(conn, tmp, f"c4{i}", company=f"Co{i}")
        agent, _ = agent_for(fixture_form_server, "upload_form.html", confirmation=link)
        apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    rows = conn.execute("SELECT confirmation_link, unverified FROM tickets WHERE status = 'applied'").fetchall()
    assert len(rows) == 3
    assert all((r[0] and r[0].strip()) or r[1] == 1 for r in rows)
