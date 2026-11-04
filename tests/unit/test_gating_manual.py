import pytest

from hireember import gating, tickets
from hireember.database import store_jobs


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_manual_job_without_resume_is_blocked_not_skipped(conn):
    url = "https://example.com/m"
    store_jobs(conn, [{"url": url, "title": "Dev", "location": "Mars"}], "example.com", "manual")
    conn.execute("UPDATE jobs SET full_description = 'x' WHERE url = ?", (url,))
    conn.commit()
    tickets.open_ticket(conn, url, "pending", "added by link")
    profile = {"personal": {"city": "Toronto", "country": "Canada"}}
    res = gating.score_job_for_ticket(conn, url, profile=profile)
    # Location was not checked, so scoring got as far as looking for a base resume.
    assert (res.status, res.reason) == ("blocked for human", "no base resume")
