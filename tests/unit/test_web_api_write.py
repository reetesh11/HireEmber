"""Dashboard HTTP server: mutating routes and updates (implementation tests)."""

import http.client
import json
import threading

import pytest

from hireember import tickets
from hireember.database import close_connection, init_db
from hireember.web.server import create_server


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    conn.execute("INSERT INTO jobs (url, title, site) VALUES ('https://j/1', 'T', 'S')")
    conn.commit()
    tid = tickets.set_job_score(conn, "https://j/1", 8, "ok")
    server = create_server("127.0.0.1", 0, db_path=db)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield conn, tid, server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    close_connection(db)


def call(port, method, path, body=None, headers=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body).encode() if body is not None else raw
    c.request(method, path, body=data, headers=headers or {})
    r = c.getresponse()
    payload = r.read()
    c.close()
    return r.status, json.loads(payload) if payload else None


def test_status_note_and_updates(env):
    conn, tid, port = env
    cursor = call(port, "GET", "/api/updates")[1]["cursor"]
    status, data = call(port, "POST", f"/api/tickets/{tid}/status", {"status": "skipped"})
    assert status == 200 and data["changed"] is True
    assert call(port, "POST", f"/api/tickets/{tid}/status", {"status": "skipped"})[1]["changed"] is False
    assert call(port, "POST", f"/api/tickets/{tid}/status", {"status": "nope"})[0] == 400
    assert call(port, "POST", f"/api/tickets/{tid}/note", {"text": "hi"}) == (200, {"ok": True})
    changes = call(port, "GET", f"/api/updates?after={cursor}")[1]["changes"]
    assert [(c["ticket_id"], c["status"]) for c in changes] == [(tid, "skipped")]


def test_bad_json_and_unknown_route(env):
    _, tid, port = env
    assert call(port, "POST", f"/api/tickets/{tid}/note", raw=b"{oops")[0] == 400
    assert call(port, "POST", "/api/nothing", {})[0] == 404
    assert call(port, "POST", "/api/answers/merge", {"keep_id": "a", "remove_id": 1})[0] == 400


def test_resume_file_upload_rejects_unsupported(env, tmp_path):
    from hireember import resumes

    conn, _, port = env
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    rid = resumes.add_resume(conn, src, "Main")
    ok = call(port, "POST", f"/api/resumes/{rid}/file", raw=b"new", headers={"X-Filename": "n.txt"})
    assert ok[0] == 200
    bad = call(port, "POST", f"/api/resumes/{rid}/file", raw=b"new", headers={"X-Filename": "n.exe"})
    assert bad[0] == 400
    assert call(port, "POST", "/api/resumes/999/file", raw=b"n", headers={"X-Filename": "n.txt"})[0] == 404
