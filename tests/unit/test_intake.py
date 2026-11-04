import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.intake import DropTally, JobFilter, mark_dropped, store_filtered, write_run_log
from hireember.runs import get_run_log

CFG = {"title_exclude": ["sales"], "title_include": ["engineer"], "location": {"accept_patterns": ["Berlin"]}}


@pytest.fixture
def conn(isolated_db):
    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_store_filtered_marks_and_never_refilters(conn):
    flt = JobFilter.load(CFG, {})
    jobs = [{"url": "a", "title": "Engineer", "location": "Berlin"},
            {"url": "b", "title": "Sales Engineer", "location": "Berlin"},
            {"url": "c", "title": "Engineer", "location": "Austin, TX"}]
    tally = DropTally()
    assert store_filtered(conn, jobs, site="S", strategy="t", flt=flt, tally=tally) == (1, 0, 2)
    assert tally.counts == {"title": 1, "location": 1}
    row = conn.execute("SELECT detail_scraped_at FROM jobs WHERE url = 'b'").fetchone()
    assert row[0] is not None
    assert conn.execute("SELECT status_reason FROM tickets WHERE job_url = 'b'").fetchone()[0] == "title: sales"
    assert store_filtered(conn, jobs, site="S", strategy="t", flt=flt) == (0, 3, 0)


def test_hint_and_log_cap(conn):
    t = DropTally()
    assert t.hint() == ""
    for i in range(22):
        t.add(f"T{i}", "title: x")
    assert t.hint(kept=0).endswith("Check your target roles and locations in Profile.")
    run_id = conn.execute("INSERT INTO runs (kind, \"trigger\", status, started_at) "
                          "VALUES ('full','manual','running','2026-01-01')").lastrowid
    write_run_log(conn, run_id, t)
    msgs = [e["message"] for e in get_run_log(conn, run_id)]
    assert msgs[0] == "Dropped 22: 22 title, 0 location" and msgs[-1] == "...and 2 more" and len(msgs) == 22
    write_run_log(conn, None, t)


def test_mark_dropped_keeps_existing_marker(conn):
    from hireember.database import store_jobs
    store_jobs(conn, [{"url": "z", "title": "T"}], "S", "t")
    mark_dropped(conn, "z", "location: X", "T")
    assert conn.execute("SELECT status FROM tickets WHERE job_url = 'z'").fetchone()[0] == "skipped"
