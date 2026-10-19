"""Phase 3 AC-11: the tailored resume is uploaded; review-before-submit stops before submit."""

import pytest

from p3_helpers import SESSION_LINK, add_ticket, agent_for, open_items, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def test_upload_uses_the_tickets_tailored_resume(env, fixture_form_server):
    from hireember.apply.attempts import get_log
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "u1")
    agent, run = agent_for(fixture_form_server, "upload_form.html")

    outcome = apply_ticket(conn, tid, agent, session_link=SESSION_LINK)

    assert outcome.result == "applied"
    assert run.uploaded == "tailored_resume.pdf"
    uploads = [r for r in get_log(conn, tid) if r["kind"] == "upload"]
    assert len(uploads) == 1 and uploads[0]["field"] == "tailored_resume.pdf"


def test_resume_path_points_at_the_pdf_of_this_ticket(env):
    from pathlib import Path

    from hireember.apply.session import GateSession
    from hireember.tickets import set_status

    conn, tmp = env
    one = add_ticket(conn, tmp, "u2")
    two = add_ticket(conn, tmp, "u3", company="Other Co")
    for tid in (one, two):
        set_status(conn, tid, "started")
        set_status(conn, tid, "applying")

    path = Path(GateSession(conn, two).resume_path())

    assert path.is_absolute() and path.exists() and path.suffix == ".pdf"
    assert path.parent == (tmp / "u3").resolve() or path.parent == tmp / "u3"


def test_resume_path_without_a_tailored_resume_raises(env):
    import pytest

    from hireember.apply.session import GateSession, SessionError
    from hireember.tickets import open_ticket, set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "u4")
    conn.execute("UPDATE tickets SET tailored_resume_path = NULL WHERE id = ?", (tid,))
    conn.commit()
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")

    with pytest.raises(SessionError) as exc:
        GateSession(conn, tid).resume_path()
    assert str(exc.value) == f"No tailored resume for ticket {tid}."
    assert open_ticket is not None


def test_review_before_submit_stops_and_queues_the_ticket(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "u5")
    agent, run = agent_for(fixture_form_server, "upload_form.html")

    outcome = apply_ticket(conn, tid, agent, review_before_submit=True, session_link=SESSION_LINK)

    assert run.submit_calls == 0
    assert outcome.result == "blocked" and outcome.reason == "review before submit"
    ticket = get_ticket(conn, tid)
    assert ticket["status"] == "blocked for human" and ticket["status_reason"] == "review before submit"
    assert not ticket["submitted_at"]
    assert [i["kind"] for i in open_items(conn, tid)] == ["review before submit"]


def test_review_setting_turns_review_on_and_the_argument_overrides_it(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket, set_setting

    conn, tmp = env
    set_setting(conn, "review_before_submit", "true")
    on = add_ticket(conn, tmp, "u6")
    agent, run_on = agent_for(fixture_form_server, "upload_form.html")
    apply_ticket(conn, on, agent, session_link=SESSION_LINK)
    assert run_on.submit_calls == 0
    assert get_ticket(conn, on)["status_reason"] == "review before submit"

    override = add_ticket(conn, tmp, "u7", company="Other Co")
    agent2, run_off = agent_for(fixture_form_server, "upload_form.html")
    apply_ticket(conn, override, agent2, review_before_submit=False, session_link=SESSION_LINK)
    assert run_off.submit_calls == 1
    assert get_ticket(conn, override)["status"] == "applied"


def test_review_is_off_by_default(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "u8")
    agent, run = agent_for(fixture_form_server, "upload_form.html")

    assert apply_ticket(conn, tid, agent, session_link=SESSION_LINK).result == "applied"
    assert run.submit_calls == 1


def test_review_user_ready_lets_the_next_run_submit(env, fixture_form_server):
    from hireember.answers import ready_queue_item
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    tid = add_ticket(conn, tmp, "u9")
    agent, _ = agent_for(fixture_form_server, "upload_form.html")
    apply_ticket(conn, tid, agent, review_before_submit=True, session_link=SESSION_LINK)
    ready_queue_item(conn, open_items(conn, tid)[0]["id"])
    agent2, run = agent_for(fixture_form_server, "upload_form.html")

    apply_ticket(conn, tid, agent2, review_before_submit=False, session_link=SESSION_LINK)

    assert run.submit_calls == 1
    assert get_ticket(conn, tid)["status"] == "applied"
