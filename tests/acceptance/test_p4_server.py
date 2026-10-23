"""Phase 4: dashboard HTTP server - localhost binding, API, editing, live updates (AC-1..9)."""

import csv
import io
import socket

import pytest

from p4_helpers import STATUSES, Client, make_ticket, seed_many, start_server, stop_server


@pytest.fixture
def env(isolated_db):
    from hireember.database import close_connection, init_db

    conn = init_db()
    server, thread = start_server(isolated_db)
    client = Client(server.server_address[1])
    yield conn, client, server
    stop_server(server, thread)
    close_connection(isolated_db)


def events(conn, tid):
    from hireember.tickets import get_history

    return get_history(conn, tid)


# -- AC-5: localhost only ---------------------------------------------------

@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "::1", "192.168.1.5", ""])
def test_create_server_refuses_other_hosts(host):
    from hireember.web.server import HostRefusedError, create_server

    with pytest.raises(HostRefusedError) as exc:
        create_server(host, 0)
    assert str(exc.value) == (f"Refusing to bind to {host}. "
                              "The dashboard is local only and binds to 127.0.0.1.")
    assert isinstance(exc.value, ValueError)


def test_defaults_and_bound_address(env):
    from hireember.web import server as srv

    _, _, server = env
    assert srv.DEFAULT_HOST == "127.0.0.1" and srv.DEFAULT_PORT == 8765
    assert server.server_address[0] == "127.0.0.1"


def test_rejects_foreign_host_and_origin(env):
    conn, client, server = env
    tid = make_ticket(conn, "hostchk", "pending")
    status, _, _ = client.request("GET", "/api/blocked", headers={"Host": "evil.example.com"})
    assert status == 403
    port = server.server_address[1]
    status, _, _ = client.request("GET", "/api/blocked", headers={"Host": f"localhost:{port}"})
    assert status == 200
    status, _, _ = client.request(
        "POST", f"/api/tickets/{tid}/note", body={"text": "x"},
        headers={"Origin": "http://evil.example.com"})
    assert status == 403
    assert events(conn, tid)[-1]["actor"] == "system"
    status, _ = client.json("POST", f"/api/tickets/{tid}/note", {"text": "ok"},
                            {"Origin": f"http://127.0.0.1:{port}"})
    assert status == 200


# -- page and listing -------------------------------------------------------

def test_index_page(env):
    _, client, _ = env
    status, headers, body = client.request("GET", "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    html = body.decode("utf-8")
    assert "<title>" in html and "HireEmber" in html.split("</title>")[0]
    for tab in ("Tickets", "Blocked", "Answers", "Resumes"):
        assert tab in html


def test_empty_database_lists_nothing(env):
    _, client, _ = env
    status, data = client.get("/api/tickets")
    assert status == 200
    assert data["tickets"] == [] and data["total"] == 0 and data["blocked_count"] == 0
    assert set(data["counts"]) == set(STATUSES)
    assert client.get("/api/blocked") == (200, {"count": 0, "items": []})


def test_api_tickets_links_counts_and_blocked_count(env):
    conn, client, _ = env
    ids = {}
    for i, s in enumerate(STATUSES):
        ids[s] = make_ticket(conn, f"api{i}", s)
    status, data = client.get("/api/tickets")
    assert status == 200
    assert data["total"] == 7 and data["blocked_count"] == 1
    assert all(v == 1 for v in data["counts"].values())
    rows = {t["id"]: t for t in data["tickets"]}
    assert rows[ids["pending"]]["link"]["label"] == "Job posting"
    assert rows[ids["applied"]]["link"] is None


def test_board_and_list_share_the_same_filtered_set(env):
    conn, client, _ = env
    for i in range(12):
        make_ticket(conn, f"same{i}", STATUSES[i % 7], company="Acme" if i % 2 else "Other",
                    score=i, created_at=f"2026-03-{i + 1:02d}T09:00:00")
    q = "company=acme&score_min=3&score_max=10&date_from=2026-03-02&date_to=2026-03-11"
    status, data = client.get(f"/api/tickets?{q}")
    assert status == 200
    assert data["total"] == len(data["tickets"]) > 0
    assert sum(data["counts"].values()) == data["total"]
    for s in STATUSES:
        assert data["counts"][s] == sum(1 for t in data["tickets"] if t["status"] == s)
    assert all(t["company"] == "Acme" and 3 <= t["score"] <= 10 for t in data["tickets"])
    status, whole = client.get("/api/tickets")
    assert whole["total"] == 12


def test_bad_filters_and_sort_are_400(env):
    _, client, _ = env
    status, data = client.get("/api/tickets?score_min=500")
    assert status == 400 and data["error"] == "Enter a whole number from 0 to 100."
    status, data = client.get("/api/tickets?date_from=2026-05-02&date_to=2026-05-01")
    assert status == 400 and data["error"] == "From date must be on or before To date."
    assert client.get("/api/tickets?sort=bogus")[0] == 400
    assert client.request("GET", "/api/export.csv?score_min=500")[0] == 400


def test_ticket_detail_history_and_blocked(env):
    from hireember import answers

    conn, client, _ = env
    tid = make_ticket(conn, "detail", "blocked for human")
    answers.queue_question(conn, tid, "unknown question", "Favourite colour?")
    conn.execute("INSERT INTO ticket_events (ticket_id, status, actor, reason, time) VALUES "
                 "(?, 'blocked for human', 'system', 'unknown question', '2999-01-01T00:00:00')",
                 (tid,))
    conn.commit()
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200
    assert data["id"] == tid and data["status"] == "blocked for human"
    assert data["history"][0]["time"] == "2999-01-01T00:00:00"
    assert data["history"][0]["actor"] == "system"
    assert data["blocked"]["reason"] == "unknown question"
    assert data["blocked"]["next_step"] == "Answer the question"
    assert data["blocked"]["question"] == "Favourite colour?"
    other = make_ticket(conn, "detail2", "pending")
    assert client.get(f"/api/tickets/{other}")[1]["blocked"] is None
    status, data = client.get("/api/tickets/99999")
    assert status == 404 and data["error"] == "Ticket 99999 not found."


# -- AC-2: blocked endpoint -------------------------------------------------

def test_blocked_endpoint_ignores_ticket_filters(env):
    conn, client, _ = env
    for i in range(3):
        make_ticket(conn, f"blk{i}", "blocked for human", status_reason="captcha")
    make_ticket(conn, "other", "pending")
    status, data = client.get("/api/blocked")
    assert status == 200 and data["count"] == 3 and len(data["items"]) == 3
    for item in data["items"]:
        assert item["reason"] and item["next_step"]
    assert client.get("/api/tickets?company=nomatch")[1]["blocked_count"] == 3


def test_answer_queue_item_endpoint(env):
    from hireember import answers

    conn, client, _ = env
    tid = make_ticket(conn, "qans", "blocked for human")
    qid = answers.queue_question(conn, tid, "unknown question", "Years of Rust?")
    status, data = client.json("POST", f"/api/queue/{qid}/answer", {"answer": "4"})
    assert status == 200 and data["saved"] is True
    assert any(a["answer"] == "4" for a in answers.list_answers(conn))
    status, data = client.json("POST", f"/api/queue/{qid}/answer", {"answer": "4"})
    assert status == 400 and data["error"]


# -- AC-3: editing ----------------------------------------------------------

def test_status_change_writes_user_event(env):
    conn, client, _ = env
    tid = make_ticket(conn, "chg", "pending")
    before = len(events(conn, tid))
    status, data = client.json("POST", f"/api/tickets/{tid}/status",
                               {"status": "started", "reason": "ready"})
    assert status == 200
    assert data == {"changed": True, "status": "started", "message": "Status changed to started."}
    hist = events(conn, tid)
    assert len(hist) == before + 1
    assert hist[-1]["actor"] == "user" and hist[-1]["status"] == "started"
    assert hist[-1]["reason"] == "ready"


def test_same_status_is_noop(env):
    conn, client, _ = env
    tid = make_ticket(conn, "same", "pending")
    before = len(events(conn, tid))
    status, data = client.json("POST", f"/api/tickets/{tid}/status", {"status": "pending"})
    assert status == 200 and data["changed"] is False
    assert data["message"] == "Ticket is already pending."
    assert len(events(conn, tid)) == before


def test_status_errors(env):
    conn, client, _ = env
    tid = make_ticket(conn, "err", "pending")
    status, data = client.json("POST", f"/api/tickets/{tid}/status", {"status": "bogus"})
    assert status == 400 and data["error"]
    assert client.json("POST", "/api/tickets/99999/status", {"status": "closed"})[0] == 404


def test_duplicate_and_override_flow(env):
    conn, client, _ = env
    first = make_ticket(conn, "dup1", "started", title="Same Role")
    second = make_ticket(conn, "dup2", "pending", title="Same Role")
    conn.execute("UPDATE jobs SET application_url = 'https://apply.example/x'")
    conn.commit()
    status, data = client.json("POST", f"/api/tickets/{second}/status", {"status": "started"})
    assert status == 409 and data["code"] == "duplicate" and data["duplicate_of"] == first
    assert data["error"]
    status, data = client.json("POST", f"/api/tickets/{second}/status",
                               {"status": "started", "override_reason": "  "})
    assert status == 400 and data["code"] == "override_reason"
    assert data["error"] == "An override needs a reason."
    status, data = client.json("POST", f"/api/tickets/{second}/status",
                               {"status": "started", "override_reason": "different team"})
    assert status == 200 and data["changed"] is True
    assert conn.execute("SELECT status FROM tickets WHERE id = ?", (second,)).fetchone()[0] == "started"


@pytest.mark.parametrize("route,column,reason", [
    ("note", "notes", "note"), ("referral-note", "referral_note", "referral note")])
def test_notes_write_event_and_column(env, route, column, reason):
    conn, client, _ = env
    tid = make_ticket(conn, f"note{route}", "applied")
    before = len(events(conn, tid))
    status, data = client.json("POST", f"/api/tickets/{tid}/{route}",
                               {"text": "<script>alert(1)</script>, \"quoted\"\nline2"})
    assert status == 200 and data == {"ok": True}
    hist = events(conn, tid)
    assert len(hist) == before + 1
    assert hist[-1]["actor"] == "user" and hist[-1]["reason"] == reason
    assert hist[-1]["status"] == "applied"
    stored = conn.execute(f"SELECT {column} FROM tickets WHERE id = ?", (tid,)).fetchone()[0]
    assert stored == "<script>alert(1)</script>, \"quoted\"\nline2"
    assert client.get(f"/api/tickets/{tid}")[1]["history"][0]["reason"] == reason


def test_note_errors(env):
    conn, client, _ = env
    tid = make_ticket(conn, "toolong", "pending")
    status, data = client.json("POST", f"/api/tickets/{tid}/note", {"text": "x" * 10001})
    assert status == 400 and data["error"] == "Note is too long (max 10,000 characters)."
    assert client.json("POST", f"/api/tickets/{tid}/note", {"text": "x" * 10000})[0] == 200
    assert client.json("POST", "/api/tickets/99999/note", {"text": "x"})[0] == 404
    assert client.json("POST", "/api/tickets/99999/referral-note", {"text": "x"})[0] == 404


# -- AC-7: live updates -----------------------------------------------------

def test_updates_cursor_and_changes(env):
    from hireember import tickets

    conn, client, _ = env
    a = make_ticket(conn, "up1", "pending")
    b = make_ticket(conn, "up2", "pending", title="Another")
    status, data = client.get("/api/updates")
    assert status == 200 and data["changes"] == []
    cursor = data["cursor"]
    assert cursor == conn.execute("SELECT MAX(id) FROM ticket_events").fetchone()[0]

    tickets.set_status(conn, a, "started", actor="system", reason="one")
    tickets.set_status(conn, a, "applying", actor="system", reason="two")
    tickets.set_status(conn, b, "closed", actor="user", reason="gone")
    status, data = client.get(f"/api/updates?after={cursor}")
    assert status == 200
    changes = {c["ticket_id"]: c for c in data["changes"]}
    assert len(data["changes"]) == 2
    assert changes[a]["status"] == "applying" and changes[b]["status"] == "closed"
    assert changes[a]["time"]
    assert data["cursor"] > cursor
    status, again = client.get(f"/api/updates?after={data['cursor']}")
    assert again["changes"] == [] and again["cursor"] == data["cursor"]


# -- AC-4: export over HTTP -------------------------------------------------

def test_export_csv_http(env):
    conn, client, _ = env
    make_ticket(conn, "ex1", company="Acme", score=9)
    make_ticket(conn, "ex2", company="Globex", score=2)
    status, headers, body = client.request("GET", "/api/export.csv?company=acme")
    assert status == 200
    assert headers["Content-Type"].startswith("text/csv")
    assert "utf-8" in headers["Content-Type"].lower()
    disp = headers["Content-Disposition"]
    assert disp.startswith('attachment; filename="hireember-tickets-') and disp.endswith('.csv"')
    assert body.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"), newline="")))
    assert rows[0] == ["company", "title", "location", "status", "score", "resume used",
                       "applied date", "links", "notes"]
    assert [r[0] for r in rows[1:]] == ["Acme"]


# -- AC-6: performance over HTTP -------------------------------------------

def test_list_endpoint_5000_tickets_under_two_seconds(env):
    conn, client, _ = env
    seed_many(conn)
    status, took = client.timed_get("/api/tickets")
    assert status == 200 and took < 2
    for col in ("company", "title", "location", "status", "score", "resume", "applied", "updated"):
        status, took = client.timed_get(f"/api/tickets?sort={col}&dir=asc")
        assert status == 200 and took < 2, col
    status, took = client.timed_get("/api/tickets?company=company&score_min=5&score_max=80")
    assert status == 200 and took < 2


def test_nothing_listens_after_server_close(isolated_db):
    server, thread = start_server(isolated_db)
    port = server.server_address[1]
    stop_server(server, thread)
    with socket.socket() as s:
        s.settimeout(1)
        assert s.connect_ex(("127.0.0.1", port)) != 0
