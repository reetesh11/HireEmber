import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "acceptance"))

from p3_helpers import SESSION_LINK, add_ticket, agent_for, make_env, open_items  # noqa: E402


def test_ready_on_review_item_skips_review_once(isolated_db, tmp_path, monkeypatch, fixture_form_server):
    from hireember.answers import ready_queue_item
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = make_env(tmp_path, monkeypatch)
    tid = add_ticket(conn, tmp, "skip1")
    agent, first = agent_for(fixture_form_server, "upload_form.html")
    apply_ticket(conn, tid, agent, review_before_submit=True, session_link=SESSION_LINK)
    assert first.submit_calls == 0
    ready_queue_item(conn, open_items(conn, tid)[0]["id"])
    agent2, run = agent_for(fixture_form_server, "upload_form.html")
    apply_ticket(conn, tid, agent2, review_before_submit=True, session_link=SESSION_LINK)
    assert run.submit_calls == 1
    assert get_ticket(conn, tid)["status"] == "applied"
