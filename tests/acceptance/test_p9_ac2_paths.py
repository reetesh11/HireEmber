"""Phase 9 AC-2: every discovery path filters before insert and stores a skipped row with the reason."""

import pytest

from p9_helpers import FILTER_CFG, Recorder, job_rows, use_config, utc  # noqa: F401


@pytest.fixture
def conn(isolated_db, tmp_path, monkeypatch):
    from hireember.database import init_db

    use_config(tmp_path, monkeypatch, searches=FILTER_CFG, profile={"personal": {}})
    return init_db()


ROLES = [
    {"title": "Backend Engineer", "url": "https://x.example/keep", "location": "Berlin"},
    {"title": "Senior Program Manager", "url": "https://x.example/title", "location": "Berlin"},
    {"title": "Data Engineer", "url": "https://x.example/loc", "location": "Austin, TX"},
]


def check_rows(conn):
    rows = job_rows(conn)
    assert set(rows) == {"https://x.example/keep", "https://x.example/title", "https://x.example/loc"}
    assert rows["https://x.example/title"]["status"] == "skipped"
    assert rows["https://x.example/title"]["reason"] == "title: program manager"
    assert rows["https://x.example/loc"]["status"] == "skipped"
    assert rows["https://x.example/loc"]["reason"].startswith("location:")
    assert rows["https://x.example/keep"]["reason"] is None or not rows["https://x.example/keep"]["reason"].startswith(
        ("title:", "location:"))
    assert rows["https://x.example/keep"]["status"] != "skipped"


def test_jobspy_dataframe_path(conn):
    import pandas as pd

    from hireember.discovery.jobspy import store_jobspy_results
    from hireember.intake import DropTally, JobFilter

    df = pd.DataFrame([{"job_url": r["url"], "title": r["title"], "location": r["location"], "site": "indeed"}
                       for r in ROLES])
    tally = DropTally()
    new, existing = store_jobspy_results(conn, df, "q", flt=JobFilter.load(), tally=tally)
    assert (new, existing) == (1, 0)
    assert tally.counts == {"title": 1, "location": 1}
    check_rows(conn)


@pytest.mark.parametrize("ats", ["workday", "careers-page"])
def test_company_paths(conn, ats):
    from hireember.companies import add_company
    from hireember.discovery.companies import discover_companies

    add_company(conn, "Alpha", "https://alpha.example/careers", ats)
    adapters = {ats: lambda company: [dict(r) for r in ROLES]}
    result = discover_companies(conn, adapters=adapters, now=utc(2026, 3, 1))
    assert result["new"] == 1 and result["dropped"] == {"title": 1, "location": 1}
    assert result["found"] == 3
    check_rows(conn)


def test_store_filtered_counts_and_never_refilters_existing(conn):
    from hireember.intake import DropTally, store_filtered

    tally = DropTally()
    jobs = [dict(r) for r in ROLES]
    assert store_filtered(conn, jobs, site="Alpha", strategy="test", tally=tally) == (1, 0, 2)
    check_rows(conn)
    assert store_filtered(conn, jobs, site="Alpha", strategy="test") == (0, 3, 0)
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 3
