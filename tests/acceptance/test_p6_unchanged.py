"""Phase 6: behaviour next to the new features that must not change (green before and after)."""

import pytest

from p6_helpers import Client, Recorder, make_ticket, make_llm, openai_body, start_server, stop_server


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


@pytest.fixture
def env(isolated_db):
    from hireember.database import close_connection, init_db

    conn = init_db()
    server, thread = start_server(isolated_db)
    yield conn, Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


def test_api_runs_keeps_its_existing_fields(env):
    from hireember.runs import execute_run

    conn, client = env
    execute_run("manual", stages=Recorder(found=6).stages(), conn=conn)
    status, data = client.get("/api/runs")
    assert status == 200
    run = data["runs"][0]
    for key in ("id", "kind", "trigger", "status", "started_at", "ended_at", "found", "scored",
                "skipped", "tickets_created", "tickets_blocked"):
        assert key in run
    assert run["found"] == 6 and run["status"] == "completed"


def test_api_ticket_detail_keeps_its_existing_fields(env):
    conn, client = env
    tid = make_ticket(conn, "keep1", "pending", company="Acme")
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200
    assert data["id"] == tid and data["status"] == "pending" and "history" in data


def test_unknown_ticket_api_is_still_404(env):
    _, client = env
    assert client.get("/api/tickets/424242")[0] == 404


def test_runs_page_with_no_runs_keeps_its_empty_state(env):
    _, client = env
    status, _, body = client.request("GET", "/runs")
    assert status == 200 and "No runs yet." in body.decode("utf-8")


def test_run_log_events_still_reach_the_database_for_a_run_and_without_one(env):
    from hireember import runs

    conn, _ = env
    runs.log_event(conn, None, "scheduler", "no run attached")
    summary = runs.execute_run("manual", stages=Recorder().stages(), conn=conn)
    runs.log_event(conn, summary.id, "score", "bad row", "warning")
    assert runs.get_run_log(conn, summary.id)[-1] == {
        "time": runs.get_run_log(conn, summary.id)[-1]["time"], "source": "score",
        "level": "warning", "message": "bad row"}


def test_llm_chat_still_returns_the_reply_text_only():
    client, fake = make_llm("m", lambda url, payload: (200, openai_body("plain reply", 3, 4)))
    assert client.chat([{"role": "user", "content": "hi"}]) == "plain reply"
    assert isinstance(client.ask("hi"), str) and fake.calls == 2


def test_attempt_log_rows_in_the_database_are_unchanged(env):
    from hireember.apply import attempts

    conn, _ = env
    tid = make_ticket(conn, "keep2")
    assert attempts.start_attempt(conn, tid) == 1
    attempts.log_step(conn, tid, 1, "fill", field="email", source="profile", detail="typed")
    row = attempts.get_log(conn, tid)[0]
    assert (row["attempt"], row["kind"], row["field"], row["source"], row["detail"]) == (
        1, "fill", "email", "profile", "typed")
    assert attempts.start_attempt(conn, tid) == 2


def test_run_continues_when_the_log_folder_cannot_be_written(conn, tmp_path, monkeypatch):
    import hireember.config as config
    from hireember import runs

    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")
    rec = Recorder(found=4)
    summary = runs.execute_run("manual", stages=rec.stages(), conn=conn)
    assert summary.status == "completed" and summary.found == 4
    assert rec.calls == ["discover", "enrich", "score", "tailor"]


def test_attempt_logging_failure_does_not_stop_the_attempt(conn, tmp_path, monkeypatch):
    import hireember.config as config
    from hireember.apply import attempts

    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")
    tid = make_ticket(conn, "a2")
    attempts.log_step(conn, tid, 1, "start")
    assert [r["kind"] for r in attempts.get_log(conn, tid)] == ["start"]
