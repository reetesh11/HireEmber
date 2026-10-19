import json

import pytest

import hireember.config as config
from hireember.apply import gate_server
from hireember.apply.session import GateSession
from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import get_ticket, set_job_score, set_status


@pytest.fixture
def env(tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"personal": {"full_name": "Test Person"}}))
    monkeypatch.setattr(config, "PROFILE_PATH", profile)
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    store_jobs(conn, [{"url": "u1", "title": "T", "company": "Acme", "location": "X"}], "S", "t")
    tid = set_job_score(conn, "u1", 8)
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")
    yield conn, GateSession(conn, tid), tid
    close_connection(db)


def test_tools_have_schema_and_description():
    assert {t["name"] for t in gate_server.TOOLS} == {
        "answer_field", "resume_path", "stop", "page_text", "before_submit",
        "submit_pressed", "submitted", "closed"}


def test_call_tool_results_are_json_and_unknown_raises(env):
    _, session, tid = env
    out = gate_server.call_tool(session, "answer_field", {"question": "Full name"})
    assert out == {"action": "fill", "value": "Test Person", "source": "profile:full_name", "reason": ""}
    assert gate_server.call_tool(session, "before_submit", {}) == {"action": "submit"}
    assert gate_server.call_tool(session, "stop", {"reason": "captcha", "page_link": "p"}) == {"ok": True}
    json.dumps(out)
    with pytest.raises(ValueError):
        gate_server.call_tool(session, "open_gmail", {})


def test_json_rpc_handler(env):
    conn, session, tid = env
    listed = gate_server._handle(session, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 8
    bad = gate_server._handle(session, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                        "params": {"name": "stop", "arguments": {"reason": "nope"}}})
    assert bad["result"]["isError"] is True
    assert gate_server._handle(session, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    gate_server._handle(session, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                  "params": {"name": "closed", "arguments": {"reason": "gone"}}})
    assert get_ticket(conn, tid)["status"] == "closed"
