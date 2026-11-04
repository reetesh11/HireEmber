"""Phase 10 AC-9: POST /api/jobs/add, POST /api/tickets/<id>/description, GET /api/stages/status results."""

import time

import pytest

from p10_helpers import Client, Pipeline, job_count, job_page_for, make_ticket, simple_html, start_server, stop_server

U1, U2, U3 = "https://example.com/jobs/1", "https://example.com/jobs/2", "https://example.com/jobs/3"


@pytest.fixture
def env(isolated_db, monkeypatch):
    from hireember import config
    from hireember.database import close_connection, init_db

    conn = init_db(isolated_db)
    config.ensure_dirs()
    server, thread = start_server(isolated_db)
    client = Client(server.server_address[1])
    yield conn, client
    wait_idle(client)
    stop_server(server, thread)
    close_connection(isolated_db)


def wait_idle(client, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        status, body = client.get("/api/stages/status")
        if status == 200 and not body["running"]:
            return body
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_run_returns_per_url_results_in_order(env, monkeypatch):
    conn, client = env
    job_page_for(monkeypatch, {U1: simple_html(1), U3: simple_html(3)}, fail={U2: "The page was not found (404)."})
    Pipeline(monkeypatch)
    status, body = client.json("POST", "/api/jobs/add", {"urls": [U1, U2, U3], "apply": False})
    assert (status, body) == (202, {"started": True})
    final = wait_idle(client)
    results = final["results"]
    assert [r["url"] for r in results] == [U1, U2, U3]
    assert [r["status"] for r in results] == ["added", "failed", "added"]
    assert set(results[0]) >= {"url", "status", "ticket_id", "score", "reason", "next_step"}
    assert results[0]["score"] == 8 and results[1]["score"] is None
    assert final["progress"] is None and "last" in final


def test_status_before_any_run_has_empty_results(env):
    _, client = env
    status, body = client.get("/api/stages/status")
    assert status == 200 and body["results"] == [] and body["running"] is False and body["progress"] is None


def test_extra_review_key_is_ignored_and_apply_uses_review(env, monkeypatch):
    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    p = Pipeline(monkeypatch)
    status, _ = client.json("POST", "/api/jobs/add", {"urls": [U1], "apply": True, "review": False})
    assert status == 202
    wait_idle(client)
    assert p.launched_urls == [U1] and p.launches[0]["review"] is True


def test_without_apply_launcher_is_not_used(env, monkeypatch):
    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    p = Pipeline(monkeypatch)
    assert client.json("POST", "/api/jobs/add", {"urls": [U1]})[0] == 202
    wait_idle(client)
    assert p.launches == []


def test_blank_lines_and_spaces_are_stripped(env, monkeypatch):
    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    status, _ = client.json("POST", "/api/jobs/add", {"urls": ["  ", f"  {U1}  ", ""]})
    assert status == 202
    results = wait_idle(client)["results"]
    assert [r["url"] for r in results] == [U1]


def test_25_urls_are_accepted(env, monkeypatch):
    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    urls = [f"https://example.com/jobs/{i}" for i in range(25)]
    assert client.json("POST", "/api/jobs/add", {"urls": urls})[0] == 202
    assert len(wait_idle(client)["results"]) == 25


@pytest.mark.parametrize("body, code, message", [
    ({"urls": [f"https://example.com/{i}" for i in range(26)]}, "too_many_urls",
     "You can add up to 25 URLs at a time."),
    ({"urls": ["https://example.com/" + "a" * 2040]}, "url_too_long", "A URL is longer than 2048 characters."),
    ({"urls": []}, "invalid_urls", "Enter at least one URL."),
    ({"urls": ["  ", ""]}, "invalid_urls", "Enter at least one URL."),
    ({"urls": [1, 2]}, "invalid_urls", "Enter at least one URL."),
    ({"urls": "https://example.com/a"}, "invalid_urls", "Enter at least one URL."),
    ({"urls": ["https://example.com/a", "https://example.com/b"], "text": "desc"}, "bad_request", None),
])
def test_validation_errors(env, monkeypatch, body, code, message):
    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    status, payload = client.json("POST", "/api/jobs/add", body)
    assert status == 400 and payload["code"] == code
    if message:
        assert payload["error"] == message
    assert job_count(conn) == 0


def test_second_start_while_running_is_refused(env, monkeypatch):
    from hireember import runs

    conn, client = env
    job_page_for(monkeypatch, default_html=simple_html(1))
    Pipeline(monkeypatch)
    token = runs.acquire_lock(conn)
    try:
        status, payload = client.json("POST", "/api/jobs/add", {"urls": [U1]})
    finally:
        runs.release_lock(conn, token)
    assert status == 409 and payload["code"] == "busy" and payload["error"] == "A run is already in progress."
    assert job_count(conn) == 0


def test_description_route_resumes_a_blocked_ticket(env, monkeypatch):
    from hireember.addjob import add_job_from_url
    from p10_helpers import failing_fetch, no_extract

    conn, client = env
    first = add_job_from_url(conn, U1, fetch=failing_fetch("The page was not found (404)."), extract=no_extract)
    p = Pipeline(monkeypatch)
    text = "Staff Engineer\nYou will lead a small team building payment systems in Python and Go every day."
    status, body = client.json("POST", f"/api/tickets/{first.ticket_id}/description", {"text": text})
    assert (status, body) == (202, {"started": True})
    results = wait_idle(client)["results"]
    assert [r["status"] for r in results] == ["added"] and results[0]["ticket_id"] == first.ticket_id
    assert [c[0] for c in p.calls] == ["score", "tailor"] and p.launches == []
    assert job_count(conn) == 1


def test_description_route_errors(env, monkeypatch):
    conn, client = env
    tid = make_ticket(conn, "blk", status="blocked for human", status_reason="x")
    status, payload = client.json("POST", f"/api/tickets/{tid}/description", {"text": "  "})
    assert status == 400 and payload["error"] == "Enter the job description."
    assert client.json("POST", "/api/tickets/99999/description", {"text": "abc"})[0] == 404


def test_start_task_async_takes_lock_and_releases_it(isolated_db):
    import threading

    from hireember import runs
    from hireember.database import close_connection, init_db

    conn = init_db(isolated_db)
    try:
        gate, seen = threading.Event(), []
        thread = runs.start_task_async("t", lambda c: (seen.append(runs.is_running(c)), gate.wait(10)), conn=conn)
        assert runs.is_running(conn)
        with pytest.raises(runs.RunInProgressError):
            runs.start_task_async("t2", lambda c: None, conn=conn)
        gate.set()
        thread.join(10)
        assert seen == [True] and not runs.is_running(conn)
    finally:
        close_connection(isolated_db)


def test_start_task_async_releases_lock_after_exception(isolated_db):
    from hireember import runs
    from hireember.database import close_connection, init_db

    conn = init_db(isolated_db)
    try:
        def work(c):
            raise RuntimeError("kaboom")

        runs.start_task_async("t", work, conn=conn).join(10)
        assert not runs.is_running(conn)
        assert "kaboom" in conn.execute("SELECT group_concat(message) FROM run_log").fetchone()[0]
    finally:
        close_connection(isolated_db)
