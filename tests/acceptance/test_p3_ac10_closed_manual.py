"""Phase 3 AC-10: a closed role closes the ticket for good; a manual-only company is never automated."""

from typer.testing import CliRunner

import pytest

from p3_helpers import SESSION_LINK, add_ticket, agent_for, forbidden_agent, open_items, widen_cli_console, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def test_closed_role_closes_the_ticket_with_the_page_reason(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "x1")
    agent, _ = agent_for(fixture_form_server, "closed_role.html")

    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert outcome.result == "closed"
    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "closed"
    assert ticket["status_reason"] == "This position is no longer accepting applications."
    assert open_items(conn, tid) == []
    assert not ticket["session_link"]


def test_closed_ticket_is_not_retried_even_after_reset_failed(env, fixture_form_server):
    from hireember.apply import launcher
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "x2")
    agent, _ = agent_for(fixture_form_server, "closed_role.html")
    apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    again = apply_ticket(conn, tid, forbidden_agent, session_link=SESSION_LINK)
    launcher.reset_failed()

    assert again.result == "skipped"
    assert get_ticket(conn, tid)["status"] == "closed"
    assert launcher.acquire_job(min_score=1) is None


def test_blank_close_reason_uses_the_default(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "x3")

    apply_ticket(conn, tid, lambda session: session.closed(""), session_link=SESSION_LINK)

    assert get_ticket(conn, tid)["status_reason"] == "closed by employer page"


def test_manual_company_goes_to_blocked_without_calling_the_agent(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket, is_manual_company, set_company_manual

    conn, tmp = env
    tid = add_ticket(conn, tmp, "x4")
    assert is_manual_company(conn, tid) is False
    set_company_manual(conn, "acme")
    assert is_manual_company(conn, tid) is True

    outcome = apply_ticket(conn, tid, forbidden_agent, session_link=SESSION_LINK)

    assert outcome.result == "blocked" and outcome.reason == "manual site"
    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human" and ticket["status_reason"] == "manual site"
    assert [i["kind"] for i in open_items(conn, tid)] == ["manual site"]


def test_manual_flag_can_be_cleared(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import is_manual_company, set_company_manual

    conn, tmp = env
    tid = add_ticket(conn, tmp, "x5")
    set_company_manual(conn, "Acme")
    set_company_manual(conn, "Acme", manual=False)
    agent, _ = agent_for(fixture_form_server, "upload_form.html")

    assert is_manual_company(conn, tid) is False
    assert apply_ticket(conn, tid, agent, session_link=SESSION_LINK).result == "applied"


def test_unknown_company_raises(env):
    import pytest

    from hireember.tickets import CompanyNotFoundError, TicketError, set_company_manual

    conn, _ = env
    with pytest.raises(CompanyNotFoundError) as exc:
        set_company_manual(conn, "Nowhere Inc")
    assert issubclass(CompanyNotFoundError, TicketError)
    assert str(exc.value) == 'No company named "Nowhere Inc".'


def test_company_commands(env, monkeypatch):
    from hireember.cli import app
    from hireember.tickets import is_manual_company

    conn, tmp = env
    widen_cli_console(monkeypatch)
    tid = add_ticket(conn, tmp, "x6")

    on = CliRunner().invoke(app, ["company", "manual", "Acme"])
    assert on.exit_code == 0, on.output
    assert 'Company "Acme" is now manual-only.' in on.output
    assert is_manual_company(conn, tid) is True

    listing = CliRunner().invoke(app, ["company", "list"])
    assert listing.exit_code == 0 and "Acme" in listing.output and "yes" in listing.output
    assert "Manual-only" in listing.output

    off = CliRunner().invoke(app, ["company", "manual", "Acme", "--off"])
    assert off.exit_code == 0
    assert 'Company "Acme" is no longer manual-only.' in off.output
    assert is_manual_company(conn, tid) is False

    missing = CliRunner().invoke(app, ["company", "manual", "Nowhere Inc"])
    assert missing.exit_code == 1
    assert 'No company named "Nowhere Inc".' in missing.output
