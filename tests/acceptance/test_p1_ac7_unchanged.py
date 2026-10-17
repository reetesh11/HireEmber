"""AC-7: existing init_db / store_jobs / get_stats behaviour is unchanged."""

import pytest

from hireember.database import close_connection, get_stats, init_db, store_jobs


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def test_store_jobs_inserts_and_skips_duplicates(conn):
    jobs = [{"url": "https://a.example/1", "title": "A"}, {"url": "https://a.example/2", "title": "B"}]
    assert store_jobs(conn, jobs, "S", "t") == (2, 0)
    assert store_jobs(conn, jobs, "S", "t") == (0, 2)
    assert store_jobs(conn, [{"url": "https://www.linkedin.com/jobs/view/1"}, {"title": "no url"}],
                      "S", "t") == (0, 0)
    assert conn.execute("SELECT title FROM jobs WHERE url='https://a.example/1'").fetchone()[0] == "A"


def test_get_stats_counts_and_init_db_idempotent(conn):
    store_jobs(conn, [{"url": "https://a.example/1", "title": "A"}], "Site", "t")
    conn2 = init_db(conn.execute("PRAGMA database_list").fetchone()[2])
    stats = get_stats(conn2)
    assert stats["total"] == 1
    assert stats["by_site"] == [("Site", 1)]
    assert stats["scored"] == 0 and stats["applied"] == 0
