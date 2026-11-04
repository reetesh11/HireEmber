import pandas as pd
import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.discovery.jobspy import store_jobspy_results
from hireember.intake import DropTally, JobFilter

CFG = {"title_exclude": ["sales"], "title_include": ["engineer"], "location": {"accept_patterns": ["Berlin"]}}


@pytest.fixture
def conn(isolated_db):
    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_dataframe_filtered_and_second_run_adds_no_work(conn):
    df = pd.DataFrame([
        {"job_url": "https://x/1", "title": "Backend Engineer", "location": "Berlin", "site": "indeed"},
        {"job_url": "https://x/2", "title": "Sales Engineer", "location": "Berlin", "site": "indeed"},
        {"job_url": "https://x/3", "title": "Data Engineer", "location": "Austin, TX", "site": "indeed"},
    ])
    flt, tally = JobFilter.load(CFG, {}), DropTally()
    assert store_jobspy_results(conn, df, "q", flt=flt, tally=tally) == (1, 0)
    assert tally.counts == {"title": 1, "location": 1}
    assert conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'skipped'").fetchone()[0] == 2
    tally2 = DropTally()
    assert store_jobspy_results(conn, df, "q", flt=flt, tally=tally2) == (0, 3)
    assert tally2.total == 0
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL").fetchone()[0] == 1
