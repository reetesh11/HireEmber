"""Phase 9 AC-6: restore dropped jobs (tickets API, HTTP route, list filtering, then enrich/score)."""

import pytest

from p9_helpers import FILTER_CFG, Client, make_ticket, start_server, stop_server, use_config

PROFILE = {"personal": {"city": "Berlin", "country": "Germany"}}


class StubClient:
    calls = 0

    def chat(self, messages, **kwargs):
        StubClient.calls += 1
        return "SCORE: 9\nKEYWORDS: a\nREASONING: Great fit."


@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    from hireember import config
    from hireember.database import close_connection, init_db
    from hireember.resumes import add_resume

    use_config(tmp_path, monkeypatch, searches=FILTER_CFG, profile=PROFILE)
    StubClient.calls = 0
    monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: StubClient())
    conn = init_db(isolated_db)
    config.ensure_dirs()
    f = tmp_path / "r.txt"
    f.write_text("RESUME Python engineer")
    add_resume(conn, f, "Base", "python")
    server, thread = start_server(isolated_db)
    yield conn, Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


_counter = [0]


def dropped_ticket(conn, reason="title: sales", location="Austin, TX"):
    from hireember import tickets
    from hireember.database import store_jobs
    from hireember.intake import mark_dropped

    _counter[0] += 1
    url = f"https://jobs.example/dropped{_counter[0]}"
    store_jobs(conn, [{"url": url, "title": "Sales Lead", "location": location}], "Alpha", "test")
    mark_dropped(conn, url, reason, "Sales Lead")
    return tickets.get_ticket_by_url(conn, url)["id"]


def test_constants_and_predicate():
    from hireember import tickets

    assert tickets.RESTORED_REASON == "restored from filter"
    assert tickets.is_dropped_reason("title: sales") and tickets.is_dropped_reason("location: Austin")
    assert not tickets.is_dropped_reason("score 3 below threshold 7")
    assert not tickets.is_dropped_reason(None)
    assert issubclass(tickets.NotRestorableError, tickets.TicketError)


@pytest.mark.parametrize("reason", ["title: sales", "location: Austin, TX"])
def test_restore_moves_to_pending(env, reason):
    from hireember import tickets

    conn, _ = env
    tid = dropped_ticket(conn, reason)
    t = tickets.restore_dropped(conn, tid)
    assert t["status"] == "pending" and t["status_reason"] == tickets.RESTORED_REASON
    assert tickets.is_restored(conn, tid) is True
    row = conn.execute("SELECT detail_scraped_at FROM jobs WHERE url = ?", (t["job_url"],)).fetchone()
    assert row[0] is None


def test_restore_rejects_other_tickets_and_repeats(env):
    from hireember import tickets

    conn, _ = env
    other = make_ticket(conn, "plain", "skipped", status_reason="score 2 below threshold 7")
    pending = make_ticket(conn, "pend", "pending")
    for tid in (other, pending):
        with pytest.raises(tickets.NotRestorableError) as exc:
            tickets.restore_dropped(conn, tid)
        assert str(exc.value) == "Only jobs dropped by the title or location filter can be restored."
    tid = dropped_ticket(conn)
    tickets.restore_dropped(conn, tid)
    with pytest.raises(tickets.NotRestorableError):
        tickets.restore_dropped(conn, tid)
    with pytest.raises(tickets.TicketNotFoundError):
        tickets.restore_dropped(conn, 99999)
    assert tickets.is_restored(conn, other) is False


def test_http_restore(env):
    conn, client = env
    tid = dropped_ticket(conn)
    status, body = client.json("POST", f"/api/tickets/{tid}/restore", {})
    assert status == 200 and body["status"] == "pending" and body["status_reason"] == "restored from filter"
    status, detail = client.get(f"/api/tickets/{tid}")
    assert detail["status"] == "pending"
    status, body = client.json("POST", f"/api/tickets/{tid}/restore", {})
    assert status == 409 and body["code"] == "not_restorable"
    assert body["error"] == "Only jobs dropped by the title or location filter can be restored."
    plain = make_ticket(conn, "plain2", "pending")
    assert client.json("POST", f"/api/tickets/{plain}/restore", {})[0] == 409
    status, body = client.json("POST", "/api/tickets/99999/restore", {})
    assert status == 404 and body == {"error": "Ticket 99999 not found.", "code": "not_found"}


def test_list_hides_dropped_unless_status_skipped(env):
    conn, client = env
    dropped = dropped_ticket(conn)
    visible = make_ticket(conn, "vis", "skipped", status_reason="score 2 below threshold 7")
    status, body = client.get("/api/tickets")
    ids = {t["id"] for t in body["tickets"]}
    assert visible in ids and dropped not in ids
    assert body["counts"].get("skipped", 0) == 1
    status, body = client.get("/api/tickets?status=skipped")
    assert {t["id"] for t in body["tickets"]} == {visible, dropped}
    status, body = client.get("/api/tickets?status=nonsense")
    assert status == 400 and body["code"] == "bad_filter"


def test_restored_job_is_scored_and_not_reskipped_by_location(env):
    from hireember import gating, tickets

    conn, _ = env
    tid = dropped_ticket(conn, "location: Austin, TX", "Austin, TX")
    url = tickets.get_ticket(conn, tid)["job_url"]
    conn.execute("UPDATE jobs SET full_description = 'desc' WHERE url = ?", (url,))
    conn.commit()
    tickets.restore_dropped(conn, tid)
    result = gating.score_job_for_ticket(conn, url, profile=PROFILE)
    assert StubClient.calls == 1
    assert result.score == 9 and result.status == "pending"
    assert not (result.reason or "").startswith("location:")


def test_db_stats_count_title_skipped(env):
    from hireember.database import get_stats

    conn, _ = env
    dropped_ticket(conn, "title: sales")
    dropped_ticket(conn, "location: Austin, TX")
    stats = get_stats(conn)
    assert stats["title_skipped"] == 1 and stats["location_skipped"] == 1
