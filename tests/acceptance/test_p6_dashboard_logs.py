"""Phase 6 AC-1: the dashboard links each run and each ticket attempt to its log text."""

import re

import pytest

from p6_helpers import Client, Recorder, make_ticket, start_server, stop_server, use_log_dir


@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    from hireember.database import close_connection, init_db

    root = use_log_dir(monkeypatch, tmp_path)
    conn = init_db()
    server, thread = start_server(isolated_db)
    client = Client(server.server_address[1])
    yield conn, client, root
    stop_server(server, thread)
    close_connection(isolated_db)


def _run(conn):
    from hireember.runs import execute_run

    return execute_run("manual", stages=Recorder().stages(), conn=conn)


# -- /logs/... --------------------------------------------------------------------

def test_run_log_url_serves_the_file_text_as_plain_text(env):
    from hireember import logs

    conn, client, _ = env
    run = _run(conn)
    logs.write_line(logs.run_log_path(run.id), "<script>alert(1)</script> & more")
    expected = logs.read_log(logs.run_log_path(run.id))
    status, headers, body = client.request("GET", f"/logs/runs/{run.id}")
    assert status == 200
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert body.decode("utf-8") == expected
    assert "<script>alert(1)</script>" in body.decode("utf-8")


def test_ticket_attempt_log_url_serves_the_file_text(env):
    from hireember import logs
    from hireember.apply import attempts

    conn, client, _ = env
    tid = make_ticket(conn, "t1")
    attempts.log_step(conn, tid, 1, "fill", field="email", source="profile", detail="ok")
    expected = logs.read_log(logs.attempt_log_path(tid, 1))
    status, headers, body = client.request("GET", f"/logs/tickets/{tid}/1")
    assert status == 200
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert body.decode("utf-8") == expected


@pytest.mark.parametrize("path", [
    "/logs/runs/999999",
    "/logs/runs/abc",
    "/logs/runs/1x",
    "/logs/runs/",
    "/logs/runs/../secret.txt",
    "/logs/runs/%2e%2e%2fsecret.txt",
    "/logs/runs/..%2fsecret.txt",
    "/logs/tickets/1/abc",
    "/logs/tickets/abc/1",
    "/logs/tickets/1/1/extra",
    "/logs/tickets/999999/1",
    "/logs/",
    "/logs/worker-0.log",
    "/logs/../secret.txt",
    "/logs/runs/1/../../secret.txt",
])
def test_other_log_paths_are_404_with_a_short_json_message(env, path):
    conn, client, root = env
    (root.parent / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    (root / "worker-0.log").write_text("worker text", encoding="utf-8")
    status, headers, body = client.request("GET", path)
    assert status == 404
    assert b"TOP SECRET" not in body and b"worker text" not in body
    assert client.json("GET", path) == (404, {"error": "Log not found.", "code": "not_found"})


# -- runs view --------------------------------------------------------------------

def test_runs_page_links_each_run_to_its_log(env):
    conn, client, _ = env
    run = _run(conn)
    status, _, body = client.request("GET", "/runs")
    text = body.decode("utf-8")
    assert status == 200
    assert re.search(r"<th[^>]*>\s*Log\s*</th>", text)
    assert f'<a href="/logs/runs/{run.id}">Log</a>' in text
    status, _, frag = client.request("GET", "/runs?fragment=1")
    assert status == 200 and f'<a href="/logs/runs/{run.id}">Log</a>' in frag.decode("utf-8")
    # the link resolves
    link_status, _, link_body = client.request("GET", f"/logs/runs/{run.id}")
    assert link_status == 200 and f"run {run.id} started" in link_body.decode("utf-8")


def test_runs_page_says_log_removed_when_the_file_is_gone(env):
    from hireember import logs

    conn, client, _ = env
    kept, gone = _run(conn), _run(conn)
    logs.run_log_path(gone.id).unlink()
    status, _, body = client.request("GET", "/runs")
    text = body.decode("utf-8")
    assert status == 200
    assert "Log removed" in text
    assert f'href="/logs/runs/{gone.id}"' not in text
    assert f'<a href="/logs/runs/{kept.id}">Log</a>' in text
    assert client.request("GET", f"/logs/runs/{gone.id}")[0] == 404


def test_api_runs_carries_log_url_and_availability(env):
    from hireember import logs

    conn, client, _ = env
    kept, gone = _run(conn), _run(conn)
    logs.run_log_path(gone.id).unlink()
    status, data = client.get("/api/runs")
    assert status == 200
    by_id = {r["id"]: r for r in data["runs"]}
    assert by_id[kept.id]["log_url"] == f"/logs/runs/{kept.id}" and by_id[kept.id]["log_available"] is True
    assert by_id[gone.id]["log_url"] == f"/logs/runs/{gone.id}" and by_id[gone.id]["log_available"] is False


# -- ticket page ------------------------------------------------------------------

def test_ticket_page_links_each_attempt_newest_first(env):
    from hireember.apply import attempts

    conn, client, _ = env
    tid = make_ticket(conn, "t2")
    attempts.log_step(conn, tid, 1, "start")
    attempts.log_step(conn, tid, 2, "start")
    status, headers, body = client.request("GET", f"/tickets/{tid}")
    text = body.decode("utf-8")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert re.search(r">\s*Logs\s*<", text)
    one = f'<a href="/logs/tickets/{tid}/1">Attempt 1 log</a>'
    two = f'<a href="/logs/tickets/{tid}/2">Attempt 2 log</a>'
    assert one in text and two in text and text.index(two) < text.index(one)
    assert "No attempt log yet." not in text
    assert client.request("GET", f"/logs/tickets/{tid}/2")[0] == 200


def test_ticket_page_without_attempts_says_no_attempt_log_yet(env):
    conn, client, _ = env
    tid = make_ticket(conn, "t3")
    status, _, body = client.request("GET", f"/tickets/{tid}")
    assert status == 200 and "No attempt log yet." in body.decode("utf-8")
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200 and data["logs"] == []


def test_ticket_page_says_log_removed_for_a_deleted_attempt_file(env):
    from hireember import logs
    from hireember.apply import attempts

    conn, client, _ = env
    tid = make_ticket(conn, "t4")
    attempts.log_step(conn, tid, 1, "start")
    attempts.log_step(conn, tid, 2, "start")
    logs.attempt_log_path(tid, 1).unlink()
    status, _, body = client.request("GET", f"/tickets/{tid}")
    text = body.decode("utf-8")
    assert status == 200
    assert "Attempt 1: Log removed" in text
    assert f'href="/logs/tickets/{tid}/1"' not in text
    assert f'<a href="/logs/tickets/{tid}/2">Attempt 2 log</a>' in text


def test_ticket_api_lists_logs_newest_first(env):
    from hireember import logs
    from hireember.apply import attempts

    conn, client, _ = env
    tid = make_ticket(conn, "t5")
    attempts.log_step(conn, tid, 1, "start")
    attempts.log_step(conn, tid, 2, "start")
    logs.attempt_log_path(tid, 1).unlink()
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200
    assert data["logs"] == [
        {"attempt": 2, "url": f"/logs/tickets/{tid}/2", "available": True},
        {"attempt": 1, "url": f"/logs/tickets/{tid}/1", "available": False},
    ]


def test_ticket_fragment_returns_only_the_extras_section(env):
    conn, client, _ = env
    tid = make_ticket(conn, "t6")
    status, _, body = client.request("GET", f"/tickets/{tid}?fragment=1")
    text = body.decode("utf-8")
    assert status == 200
    assert '<section id="ticket-extras"' in text
    assert "<html" not in text.lower() and "No attempt log yet." in text
    full = client.request("GET", f"/tickets/{tid}")[2].decode("utf-8")
    assert "<html" in full.lower() and '<section id="ticket-extras"' in full

