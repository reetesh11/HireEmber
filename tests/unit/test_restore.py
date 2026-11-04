import pytest

from hireember import tickets
from hireember.database import close_connection, get_jobs_by_stage, get_stats, init_db, store_jobs


@pytest.fixture
def conn(isolated_db):
    c = init_db(isolated_db)
    yield c
    close_connection(isolated_db)


def _dropped(conn, url, reason):
    store_jobs(conn, [{"url": url, "title": "T", "location": "X"}], "S", "t")
    conn.execute("UPDATE jobs SET detail_scraped_at = 'now', full_description = 'd' WHERE url = ?", (url,))
    return tickets.open_ticket(conn, url, "skipped", reason)


def test_restore_and_sticky(conn):
    tid = _dropped(conn, "u1", "title: sales")
    t = tickets.restore_dropped(conn, tid)
    assert t["status"] == "pending" and tickets.is_restored(conn, tid)
    with pytest.raises(tickets.NotRestorableError):
        tickets.restore_dropped(conn, tid)
    with pytest.raises(tickets.TicketNotFoundError):
        tickets.restore_dropped(conn, 999)


def test_restore_clears_marker_without_description(conn):
    tid = _dropped(conn, "u2", "location: X")
    conn.execute("UPDATE jobs SET full_description = NULL WHERE url = 'u2'")
    tickets.restore_dropped(conn, tid)
    assert conn.execute("SELECT detail_scraped_at FROM jobs WHERE url = 'u2'").fetchone()[0] is None


def test_pending_score_excludes_dropped_and_stats(conn):
    _dropped(conn, "u3", "title: sales")
    _dropped(conn, "u4", "location: X")
    store_jobs(conn, [{"url": "u5", "title": "T", "location": "X"}], "S", "t")
    conn.execute("UPDATE jobs SET full_description = 'd' WHERE url = 'u5'")
    assert [j["url"] for j in get_jobs_by_stage(conn, "pending_score")] == ["u5"]
    stats = get_stats(conn)
    assert stats["title_skipped"] == 1 and stats["location_skipped"] == 1
