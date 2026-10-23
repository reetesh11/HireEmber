"""Phase 5 CLI (schedule, export, help, stage commands), export and dashboard
(AC-7, AC-9, AC-12, AC-13, AC-14)."""

import csv
import io
import json
import threading
import time

import pytest
from typer.testing import CliRunner

from p4_helpers import Client, stop_server
from p5_helpers import Recorder, blocking_stages, make_ticket, utc


def invoke(*args):
    from hireember.cli import app

    return CliRunner().invoke(app, list(args))


def flat(result):
    return " ".join(result.output.split())


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


# -- AC-7: help on a fresh install -------------------------------------------

@pytest.mark.parametrize("cmd", [["schedule"], ["scheduler"], ["export"]])
def test_help_exits_zero(isolated_db, cmd):
    r = invoke(*cmd, "--help")
    assert r.exit_code == 0, r.output
    assert r.output.strip()
    assert not isolated_db.exists()


def test_top_level_help_lists_new_commands():
    r = invoke("--help")
    assert r.exit_code == 0
    for name in ("schedule", "scheduler", "export"):
        assert name in r.output


# -- AC-13: schedule command ---------------------------------------------------

def test_schedule_set_show_off(isolated_db):
    r = invoke("schedule")
    assert r.exit_code == 0 and "No schedule set." in flat(r)
    assert "Scheduled applying: off." in flat(r)
    r = invoke("schedule", "--at", "18:30", "--at", "08:00", "--at", "08:00")
    assert r.exit_code == 0, r.output
    assert "Schedule set: daily at 08:00, 18:30." in flat(r)
    assert "hireember scheduler" in flat(r)
    r = invoke("schedule")
    assert "Scheduled daily at 08:00, 18:30." in flat(r)
    r = invoke("schedule", "--apply", "on", "--apply-limit", "7")
    assert r.exit_code == 0
    assert "Scheduled applying: on (up to 7 per day)." in flat(r)
    r = invoke("schedule", "--apply", "maybe")
    assert r.exit_code == 1
    r = invoke("schedule", "--off")
    assert r.exit_code == 0 and "Schedule cleared." in flat(r)
    assert "No schedule set." in flat(invoke("schedule"))


def test_schedule_invalid_time_leaves_schedule_unchanged(isolated_db):
    invoke("schedule", "--at", "08:00")
    r = invoke("schedule", "--at", "25:00")
    assert r.exit_code == 1
    assert 'Invalid time "25:00". Use 24-hour HH:MM, e.g. 08:00.' in flat(r)
    assert "Scheduled daily at 08:00." in flat(invoke("schedule"))


def test_scheduler_once_exits_zero(isolated_db):
    r = invoke("scheduler", "--once")
    assert r.exit_code == 0, r.output


# -- AC-12: CLI stage commands -------------------------------------------------

def test_cli_run_stage_rejected_when_run_in_progress(conn):
    from hireember.runs import execute_run

    entered, release = threading.Event(), threading.Event()
    t = threading.Thread(
        target=lambda: execute_run("manual", stages=blocking_stages(entered, release).stages()),
        daemon=True)
    t.start()
    try:
        assert entered.wait(10)
        r = invoke("run", "discover")
        assert r.exit_code == 1
        assert "A run is already in progress." in flat(r)
    finally:
        release.set()
        t.join(15)


# -- AC-14: export -------------------------------------------------------------

def test_export_csv_header_and_rows(conn, tmp_path):
    from hireember.export import export_csv
    from hireember.runs import execute_run
    from hireember.web.queries import tickets_csv

    out = tmp_path / "out"
    out.mkdir()
    results = export_csv(conn, out)
    assert [(p.name, n) for p, n in results] == [("tickets.csv", 0), ("runs.csv", 0)]
    runs_header = "id,kind,trigger,status,started_at,ended_at,found,scored,skipped," \
                  "tickets_created,tickets_blocked"
    assert (out / "runs.csv").read_text(encoding="utf-8").strip() == runs_header
    assert (out / "tickets.csv").read_text(encoding="utf-8") == tickets_csv(conn)

    make_ticket(conn, "t1")
    execute_run("manual", stages=Recorder(found=3, scored=2, skipped=1).stages(), conn=conn,
                now=utc(2026, 1, 1, 8))
    execute_run("scheduled", stages=Recorder(found=8).stages(), conn=conn, now=utc(2026, 1, 2, 8))
    results = export_csv(conn, out)
    assert [n for _, n in results] == [1, 2]
    rows = list(csv.DictReader(io.StringIO((out / "runs.csv").read_text(encoding="utf-8"))))
    assert [r["found"] for r in rows] == ["3", "8"]
    assert [r["trigger"] for r in rows] == ["manual", "scheduled"]
    assert (out / "tickets.csv").read_text(encoding="utf-8") == tickets_csv(conn)


def test_export_bad_directory_raises_and_writes_nothing(conn, tmp_path):
    from hireember.export import ExportError, export_csv

    missing = tmp_path / "nope"
    with pytest.raises(ExportError):
        export_csv(conn, missing)
    assert not missing.exists()
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    with pytest.raises(ExportError):
        export_csv(conn, a_file)


def test_cli_export(isolated_db, tmp_path):
    out = tmp_path / "exp"
    out.mkdir()
    r = invoke("export", "--out", str(out))
    assert r.exit_code == 0, r.output
    text = flat(r)
    assert f"Wrote {out / 'tickets.csv'} (0 rows)." in text
    assert f"Wrote {out / 'runs.csv'} (0 rows)." in text
    assert (out / "tickets.csv").exists() and (out / "runs.csv").exists()
    r = invoke("export", "--out", str(tmp_path / "missing"))
    assert r.exit_code == 1
    assert not (tmp_path / "missing").exists()


# -- dashboard -----------------------------------------------------------------

@pytest.fixture
def web(isolated_db):
    from hireember.database import close_connection, init_db
    from hireember.web.server import create_server

    conn = init_db()
    rec = Recorder(found=1, new=1, scored=1, skipped=0, created=0, blocked=0, submitted=2)
    server = create_server("127.0.0.1", 0, db_path=isolated_db, stages=rec.stages())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield conn, Client(server.server_address[1]), rec
    stop_server(server, thread)
    close_connection(isolated_db)


def test_runs_page_empty_state(web):
    _, client, _ = web
    status, headers, body = client.request("GET", "/runs")
    text = body.decode()
    assert status == 200 and "text/html" in headers.get("Content-Type", "")
    assert "Runs" in text and "No runs yet." in text


def test_runs_page_shows_counts_newest_first_and_escapes(web):
    from hireember.runs import execute_run

    conn, client, _ = web
    execute_run("manual", stages=Recorder(found=111, scored=222, skipped=333, created=0,
                                          blocked=0).stages(), conn=conn, now=utc(2026, 1, 1, 8))
    execute_run("scheduled", stages=Recorder(found=444, scored=555, skipped=666).stages(),
                conn=conn, now=utc(2026, 1, 2, 8))
    status, _, body = client.request("GET", "/runs")
    text = body.decode()
    assert status == 200 and "No runs yet." not in text
    squashed = "".join(text.split())
    for n in (111, 222, 333, 444, 555, 666):
        assert f">{n}<" in squashed
    assert squashed.index(">444<") < squashed.index(">111<")
    assert "scheduled" in text and "manual" in text
    status, _, frag = client.request("GET", "/runs?fragment=1")
    assert status == 200 and "<html" not in frag.decode().lower() and "444" in frag.decode()


def test_api_runs(web):
    from hireember.runs import execute_run

    conn, client, _ = web
    execute_run("manual", stages=Recorder(found=5).stages(), conn=conn, now=utc(2026, 1, 1, 8))
    execute_run("manual", stages=Recorder(found=6).stages(), conn=conn, now=utc(2026, 1, 2, 8))
    status, data = client.get("/api/runs")
    assert status == 200
    assert [r["found"] for r in data["runs"]] == [6, 5]
    assert set(data["runs"][0]) == {"id", "kind", "trigger", "status", "started_at", "ended_at",
                                    "found", "scored", "skipped", "tickets_created",
                                    "tickets_blocked"}


def test_index_has_runs_tab_and_stage_buttons():
    from importlib import resources

    html = (resources.files("hireember.web") / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="tab-runs"' in html
    for label in ("Run discover", "Run score", "Run tailor", "Run apply"):
        assert label in html
    assert "A run is already in progress." in html


def test_post_stage_starts_only_that_stage(web):
    _, client, rec = web
    status, data = client.json("POST", "/api/stages/score", {})
    assert status == 202 and data == {"started": True, "stage": "score"}
    deadline = time.time() + 10
    while time.time() < deadline:
        _, st = client.get("/api/stages/status")
        if not st["running"] and st["last"]:
            break
        time.sleep(0.05)
    assert st["running"] is False
    assert st["last"]["stage"] == "score" and st["last"]["message"] == "score: 1 scored, 0 skipped."
    assert rec.calls == ["score"]
    status, data = client.json("POST", "/api/stages/apply", {"limit": 4})
    assert status == 202
    deadline = time.time() + 10
    while time.time() < deadline and rec.calls != ["score", "apply"]:
        time.sleep(0.05)
    assert rec.calls == ["score", "apply"] and rec.apply_limits == [4]


def test_post_stage_unknown_and_busy(web):
    conn, client, _ = web
    status, data = client.json("POST", "/api/stages/enrich")
    assert status == 404 and data["code"] == "not_found"

    from hireember.runs import execute_run

    entered, release = threading.Event(), threading.Event()
    t = threading.Thread(
        target=lambda: execute_run("manual", stages=blocking_stages(entered, release).stages()),
        daemon=True)
    t.start()
    try:
        assert entered.wait(10)
        status, data = client.json("POST", "/api/stages/discover")
        assert status == 409
        assert data == {"error": "A run is already in progress.", "code": "run_in_progress"}
        _, st = client.get("/api/stages/status")
        assert st["running"] is True
    finally:
        release.set()
        t.join(15)
    assert json.dumps(st)
