import atexit
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import hireember.apply.chrome as chrome_mod
import hireember.config as config
from hireember.apply import dashboard, launcher
from hireember.cli import app
from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import get_ticket, set_job_score, set_status

atexit.unregister(chrome_mod.cleanup_on_exit)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def conn(isolated_db, tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"personal": {"full_name": "T P", "email": "t@x.io"}}))
    monkeypatch.setattr(config, "PROFILE_PATH", profile)
    c = init_db()
    yield c
    close_connection()


def add(conn, n, company="Acme", score=8):
    store_jobs(conn, [{"url": f"https://j/{n}", "title": f"T{n}", "company": company,
                       "location": f"L{n}"}], "S", "t")
    conn.execute("UPDATE jobs SET tailored_resume_path = '/x/r.txt' WHERE url = ?", (f"https://j/{n}",))
    conn.commit()
    return set_job_score(conn, f"https://j/{n}", score)


def test_mcp_config_and_tools():
    cfg = launcher.build_mcp_config(9222, 5)
    assert set(cfg["mcpServers"]) == {"playwright", "hireember"}
    gate = cfg["mcpServers"]["hireember"]
    assert gate["command"] == sys.executable
    assert gate["args"] == ["-m", "hireember.apply.gate_server", "--ticket", "5"]
    assert "--review" in launcher.build_mcp_config(9222, 5, True)["mcpServers"]["hireember"]["args"]
    assert launcher.agent_tools() == ["mcp__playwright", "mcp__hireember"]
    assert "gmail" not in json.dumps(cfg).lower()


def test_acquire_skips_blocked_closed_held_and_takes_ticketless(conn):
    blocked, closed, held, ok = (add(conn, i) for i in range(4))
    set_status(conn, blocked, "blocked for human", reason="captcha")
    set_status(conn, closed, "closed", reason="gone")
    conn.execute("UPDATE tickets SET not_before = '2999-01-01T00:00:00+00:00' WHERE id = ?", (held,))
    conn.commit()
    conn.execute("INSERT INTO jobs (url, title, site, tailored_resume_path, fit_score) "
                 "VALUES ('https://j/plain', 'P', 'indeed', '/x/r.txt', 6)")
    conn.commit()
    assert launcher.acquire_job(min_score=1)["url"] == "https://j/3"
    assert launcher.acquire_job(min_score=1)["url"] == "https://j/plain"
    assert launcher.acquire_job(min_score=1) is None
    assert ok == get_ticket(conn, ok)["id"]


def test_worker_loop_applied_blocked_and_closed_outcomes(conn, monkeypatch):
    add(conn, 1, "A", 9)
    add(conn, 2, "B", 8)
    add(conn, 3, "C", 7)
    steps = iter(["submit", "stop", "close"])

    def fake_run_job(job, port, worker_id=0, model="sonnet", dry_run=False, session=None):
        step = next(steps)
        if step == "submit":
            session.submit_pressed()
            session.submitted("https://ok")
            return "applied", 5
        if step == "stop":
            session.stop("captcha", "http://p")
            return "blocked", 5
        session.closed("Position closed.")
        return "expired", 5

    monkeypatch.setattr(launcher, "launch_chrome", lambda *a, **k: None)
    monkeypatch.setattr(launcher, "run_job", fake_run_job)
    dashboard.init_worker(0)

    result = launcher.worker_loop(worker_id=0, limit=3, min_score=1)

    assert result == (1, 0)
    rows = {r["url"]: (r["apply_status"], r["apply_error"]) for r in
            conn.execute("SELECT url, apply_status, apply_error FROM jobs")}
    assert rows["https://j/1"][0] == "applied"
    assert rows["https://j/2"][0] is None
    assert rows["https://j/3"] == ("expired", "Position closed.")


def test_main_recovers_and_checks_profiles(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(chrome_mod, "check_worker_profiles", lambda n: calls.append(("check", n)))
    monkeypatch.setattr(launcher, "recover_stale_tickets", lambda c: calls.append(("recover",)))
    monkeypatch.setattr(launcher, "init_worker", lambda i: (_ for _ in ()).throw(RuntimeError("stop")))
    with pytest.raises(RuntimeError):
        launcher.main(workers=2)
    assert calls == [("check", 2), ("recover",)]


def test_cli_apply_help_lists_review():
    assert "--review" in CliRunner().invoke(app, ["apply", "--help"]).output


def test_status_shows_held_tickets(conn):
    held = add(conn, 1)
    conn.execute("UPDATE tickets SET status_reason = 'limit: daily', not_before = ? WHERE id = ?",
                 ("2026-10-19T00:00:00+00:00", held))
    conn.commit()
    out = CliRunner().invoke(app, ["status"], terminal_width=200).output
    assert "limit: daily" in out and "2026-10-19 00:00" in out


def test_src_has_no_capsolver_or_gmail():
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "capsolver" not in text and "gmail" not in text, path
