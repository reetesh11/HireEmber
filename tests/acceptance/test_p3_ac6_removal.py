"""Phase 3 AC-6: no CAPTCHA solver, no signup/login/mail routine, no mail tool in a default run."""

import json
import re
import subprocess

import pytest

from p3_helpers import REPO_ROOT, add_ticket, make_env

FORBIDDEN_PROMPT = (
    "capsolver", "gmail", "send_email", "search_emails", "read_email", "verification code",
    "sign up", "signup", "create an account", "create account",
)
REQUIRED_PROMPT = ("answer_field", "stop", "before_submit", "submit_pressed", "submitted", "closed")

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _tracked_text_files(*roots):
    out = subprocess.run(["git", "ls-files", *roots], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    files = []
    for rel in out.stdout.split():
        path = REPO_ROOT / rel
        if path.is_file():
            try:
                files.append((rel, path.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                continue
    return files


def test_no_capsolver_anywhere_in_source_docs_or_config():
    hits = []
    for rel, text in _tracked_text_files("src", "README.md", ".env.example", "pyproject.toml"):
        if re.search(r"capsolver", text, re.I):
            hits.append(rel)
    assert hits == []


def test_doctor_has_no_capsolver_check(env):
    from hireember.doctor import run_checks

    names = [c.name for c in run_checks()]
    assert not any("capsolver" in n.lower() for n in names)
    assert len(names) == 13


def test_prompt_has_no_signup_login_or_mail_instructions(env, tmp_path, monkeypatch):
    import hireember.config as config
    from hireember.apply.prompt import build_prompt

    profile = json.loads((REPO_ROOT / "profile.example.json").read_text(encoding="utf-8"))
    profile["personal"].update(full_name="Test Person", email="test@example.com", phone="555-0100",
                               password="hunter2-never-in-prompt")
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    resume = tmp_path / "tailored.txt"
    resume.write_text("Test Person", encoding="utf-8")
    resume.with_suffix(".pdf").write_bytes(b"%PDF-1.4\n")
    job = {"url": "https://jobs.example/p1", "title": "Backend Engineer", "site": "Acme",
           "application_url": "https://jobs.example/p1/apply", "fit_score": 8,
           "tailored_resume_path": str(resume), "location": "Berlin", "full_description": "Build APIs."}

    text = build_prompt(job, "Test Person\nBackend engineer").lower()

    for word in FORBIDDEN_PROMPT:
        assert word not in text, f"prompt still mentions {word!r}"
    assert "hunter2-never-in-prompt" not in text
    for word in REQUIRED_PROMPT:
        assert word in text, f"prompt does not mention {word!r}"


def test_default_mcp_config_and_tool_list_have_no_mail_tool():
    from hireember.apply.launcher import agent_tools, build_mcp_config

    config = build_mcp_config(9222, 7)

    assert set(config["mcpServers"]) == {"playwright", "hireember"}
    server = config["mcpServers"]["hireember"]
    joined = " ".join([server["command"], *server["args"]])
    assert "hireember.apply.gate_server" in joined and "--ticket" in server["args"] and "7" in server["args"]
    assert "gmail" not in json.dumps(config).lower()
    tools = agent_tools()
    assert tools and not any("mail" in t.lower() for t in tools)
    assert any(t.startswith("mcp__playwright") for t in tools)
    assert any(t.startswith("mcp__hireember") for t in tools)


def test_gate_server_tools_cover_the_session_surface():
    from hireember.apply.gate_server import TOOLS

    names = {t["name"] for t in TOOLS}
    assert names == {"answer_field", "resume_path", "stop", "page_text", "before_submit",
                     "submit_pressed", "submitted", "closed"}
    assert all("inputSchema" in t and t.get("description") for t in TOOLS)


def test_gate_server_call_tool_drives_the_session(env):
    import pytest

    from hireember.apply.gate_server import call_tool
    from hireember.apply.session import GateSession
    from hireember.tickets import get_ticket, set_status

    conn, tmp = env
    tid = add_ticket(conn, tmp, "m1")
    set_status(conn, tid, "started")
    set_status(conn, tid, "applying")
    session = GateSession(conn, tid)

    fill = call_tool(session, "answer_field", {"question": "Full name", "field_type": "text"})
    stop = call_tool(session, "answer_field", {"question": "Password", "field_type": "password"})

    assert fill["action"] == "fill" and fill["value"] == "Test Person" and fill["source"].startswith("profile:")
    assert stop["action"] == "stop" and stop["value"] is None
    assert get_ticket(conn, tid)["status"] == "blocked for human"
    json.dumps(fill)
    with pytest.raises(ValueError):
        call_tool(session, "open_gmail", {})
