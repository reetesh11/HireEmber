"""Phase 9 AC-12: behaviour that must not change (remote, empty, placeholder locations; no lists = keep all)."""

import pytest

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
CFG = {"locations": [{"location": "Toronto, ON", "remote": True}], "location": {"accept_patterns": ["Toronto"]}}


def skip(location, cfg=CFG):
    from hireember.location import location_skip_reason

    return location_skip_reason(location, PROFILE, cfg)


@pytest.mark.parametrize("location", ["Remote", "Remote - US", "", None, "N/A", "TBD", "Worldwide", "Various"])
def test_remote_empty_and_placeholder_pass(location):
    assert skip(location) is None


def test_recognised_foreign_location_still_skipped():
    assert skip("Austin, TX") == "location: Austin, TX"
    assert skip("Ottawa, ON") is None


def test_store_jobs_unchanged(isolated_db):
    from hireember.database import init_db, store_jobs

    conn = init_db()
    jobs = [{"url": "https://t.example/1", "title": "Sales Lead", "location": "Austin, TX"}]
    assert store_jobs(conn, jobs, "Site", "test") == (1, 0)
    assert store_jobs(conn, jobs, "Site", "test") == (0, 1)


def test_no_title_or_location_config_keeps_every_company_job(isolated_db, tmp_path, monkeypatch):
    from hireember.companies import add_company
    from hireember.database import init_db
    from hireember.discovery.companies import discover_companies
    from p9_helpers import use_config

    use_config(tmp_path, monkeypatch, searches={"queries": []}, profile={"personal": {}})
    conn = init_db()
    add_company(conn, "Alpha", "https://alpha.example/careers", "workday")
    roles = [{"title": "Sales Lead", "url": "https://a.example/1", "location": "Austin, TX"},
             {"title": "Engineer", "url": "https://a.example/2", "location": "Berlin"}]
    result = discover_companies(conn, adapters={"workday": lambda c: [dict(r) for r in roles]})
    assert result["found"] == 2 and result["new"] == 2
    assert conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'skipped'").fetchone()[0] == 0
