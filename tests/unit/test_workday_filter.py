import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.discovery import workday
from hireember.intake import DropTally, JobFilter

EMP = {"acme": {"name": "Acme", "tenant": "t", "site_id": "S", "base_url": "https://acme.example"}}
RESPONSE = {"total": 3, "jobPostings": [
    {"title": "Backend Engineer", "locationsText": "Berlin", "externalPath": "/job/1"},
    {"title": "Sales Manager", "locationsText": "Berlin", "externalPath": "/job/2"},
    {"title": "Data Engineer", "locationsText": "Austin, TX", "externalPath": "/job/3"},
]}
CFG = {"title_exclude": ["sales"], "title_include": ["engineer"], "location": {"accept_patterns": ["Berlin"]}}


@pytest.fixture
def conn(isolated_db):
    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_workday_response_is_filtered_before_insert(conn, monkeypatch):
    monkeypatch.setattr(workday, "workday_search", lambda *a, **k: RESPONSE)
    jobs = workday.search_employer("acme", EMP["acme"], "x")
    assert len(jobs) == 3  # no location filtering inside the search any more
    for j in jobs:
        j["full_description"] = "d" * 300
    tally = DropTally()
    assert workday.store_results(conn, jobs, EMP, JobFilter.load(CFG, {}), tally) == (1, 0)
    assert tally.counts == {"title": 1, "location": 1}
    rows = {r["url"]: r for r in conn.execute("SELECT url, full_description, detail_scraped_at FROM jobs")}
    assert rows["https://acme.example/S/job/1"]["full_description"]
    tickets = dict(conn.execute("SELECT job_url, status_reason FROM tickets").fetchall())
    assert tickets["https://acme.example/S/job/2"] == "title: sales"
    assert tickets["https://acme.example/S/job/3"].startswith("location:")
    assert workday.store_results(conn, jobs, EMP, JobFilter.load(CFG, {}), tally) == (0, 3)
