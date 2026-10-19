"""Phase 3 AC-3: a duplicate ticket never opens a browser."""

import pytest

from p3_helpers import SESSION_LINK, add_ticket, forbidden_agent, make_env

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _duplicate_pair(conn, tmp):
    from hireember.tickets import set_status

    first = add_ticket(conn, tmp, "d1", title="Backend Engineer", location="Berlin")
    second = add_ticket(conn, tmp, "d2", title="Backend Engineer", location="Berlin")
    set_status(conn, first, "started")
    return first, second


def test_apply_ticket_returns_duplicate_without_calling_the_agent(env):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket

    conn, tmp = env
    first, second = _duplicate_pair(conn, tmp)

    outcome = apply_ticket(conn, second, forbidden_agent, session_link=SESSION_LINK)

    assert outcome.result == "duplicate"
    ticket = get_ticket(conn, second)
    assert ticket["status"] == "blocked for human"
    assert ticket["status_reason"] == "duplicate"
    assert ticket["duplicate_of"] == first


def test_worker_loop_never_launches_chrome_or_claude_for_a_duplicate(env, monkeypatch):
    import hireember.apply.chrome as chrome_mod
    from hireember.apply import dashboard, launcher
    from hireember.tickets import get_ticket, set_status

    conn, tmp = env
    first, second = _duplicate_pair(conn, tmp)
    set_status(conn, first, "applying")
    set_status(conn, first, "applied")
    conn.execute("UPDATE jobs SET apply_status = 'applied' WHERE url = 'https://jobs.example/d1'")
    conn.commit()
    calls = []
    monkeypatch.setattr(launcher, "launch_chrome", lambda *a, **k: calls.append("launch_chrome"))
    monkeypatch.setattr(launcher, "run_job", lambda *a, **k: calls.append("run_job") or ("failed:stub", 0))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: calls.append("Popen"))
    monkeypatch.setattr(chrome_mod, "launch_chrome", lambda *a, **k: calls.append("chrome.launch_chrome"))
    dashboard.init_worker(0)

    launcher.worker_loop(worker_id=0, limit=1, min_score=7)

    assert calls == []
    ticket = get_ticket(conn, second)
    assert ticket["status"] == "blocked for human" and ticket["status_reason"] == "duplicate"
