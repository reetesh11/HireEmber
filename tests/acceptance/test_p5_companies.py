"""Phase 5 company list and discovery over it (AC-4, AC-5, AC-6)."""

import pytest
from typer.testing import CliRunner

from p5_helpers import Recorder, run_rows, utc

EMPTY_MESSAGE = "No companies to search. Add one with `hireember company add`."


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def make_adapters(roles_by_company, failing=(), seen=None):
    seen = seen if seen is not None else []

    def adapter_for(_ats):
        def adapter(company):
            seen.append(company["name"])
            if company["name"] in failing:
                raise RuntimeError(f"{company['name']} is down")
            return [dict(r) for r in roles_by_company[company["name"]]]
        return adapter

    return {"workday": adapter_for("workday"), "careers-page": adapter_for("careers-page")}, seen


ROLES = {
    "Alpha": [{"title": "Backend Engineer", "url": "https://alpha.example/1", "location": "Berlin"},
              {"title": "Data Engineer", "url": "https://alpha.example/2", "location": "Remote"}],
    "Beta": [{"title": "SRE", "url": "https://beta.example/1", "location": "Paris"}],
    "Gamma": [{"title": "Designer", "url": "https://gamma.example/1", "location": "Rome"},
              {"title": "PM", "url": "https://gamma.example/2", "location": "Oslo"}],
}


def add_three(conn):
    from hireember.companies import add_company

    add_company(conn, "Alpha", "https://alpha.example/careers", "workday")
    add_company(conn, "Beta", "https://beta.example/careers", "careers-page")
    add_company(conn, "Gamma", "https://gamma.example/careers", "workday")


def test_add_remove_search_list(conn):
    from hireember.companies import (ATS_TYPES, CompanyExistsError, CompanyMissingError,
                                     UnknownAtsError, add_company, remove_company, search_list)
    from hireember.tickets import TicketError, list_companies

    assert ATS_TYPES == ("workday", "careers-page")
    cid = add_company(conn, "Acme", "https://acme.example/jobs", "workday")
    assert [c["name"] for c in search_list(conn)] == ["Acme"]
    assert set(search_list(conn)[0]) >= {"id", "name", "careers_url", "ats_type"}
    assert search_list(conn)[0]["id"] == cid
    row = list_companies(conn)[0]
    assert row["careers_url"] == "https://acme.example/jobs" and row["ats_type"] == "workday"
    with pytest.raises(CompanyExistsError) as exc:
        add_company(conn, "ACME", "https://x.example", "workday")
    assert isinstance(exc.value, TicketError)
    remove_company(conn, "Acme")
    assert search_list(conn) == [] and list_companies(conn) == []
    with pytest.raises(CompanyMissingError):
        remove_company(conn, "Acme")
    with pytest.raises(CompanyMissingError):
        remove_company(conn, "Nobody")
    again = add_company(conn, "Acme", "https://new.example/jobs", "careers-page")
    assert again == cid
    assert search_list(conn)[0]["careers_url"] == "https://new.example/jobs"
    with pytest.raises(UnknownAtsError) as exc2:
        add_company(conn, "Zed", "https://z.example", "taleo")
    assert str(exc2.value) == 'Unknown ATS type "taleo". Valid types: workday, careers-page.'


def test_discovery_stores_roles_with_all_fields(conn):
    from hireember.discovery.companies import discover_companies

    add_three(conn)
    adapters, _ = make_adapters(ROLES)
    result = discover_companies(conn, adapters=adapters, now=utc(2026, 3, 1, 8))
    assert result["found"] == 5 and result["new"] == 5 and result["companies"] == 3
    assert result["failures"] == []
    rows = conn.execute(
        "SELECT j.url, j.title, j.location, j.site, j.discovered_at, j.last_seen_at, c.name "
        "FROM jobs j LEFT JOIN companies c ON c.id = j.company_id ORDER BY j.url").fetchall()
    assert len(rows) == 5
    for r in rows:
        assert r["name"] and r["title"] and r["location"] and r["site"] and r["url"]
        assert r["discovered_at"] and r["last_seen_at"]
        assert r["site"] == r["name"]
    assert {r["name"] for r in rows} == {"Alpha", "Beta", "Gamma"}


def test_rediscovery_updates_last_seen_keeps_date_found(conn):
    from hireember.discovery.companies import discover_companies

    add_three(conn)
    adapters, _ = make_adapters(ROLES)
    discover_companies(conn, adapters=adapters, now=utc(2026, 3, 1, 8))
    first = {r["url"]: (r["discovered_at"], r["last_seen_at"])
             for r in conn.execute("SELECT url, discovered_at, last_seen_at FROM jobs")}
    result = discover_companies(conn, adapters=adapters, now=utc(2026, 3, 2, 8))
    assert result["new"] == 0 and result["existing"] == 5
    rows = conn.execute("SELECT url, discovered_at, last_seen_at FROM jobs").fetchall()
    assert len(rows) == 5
    for r in rows:
        assert r["discovered_at"] == first[r["url"]][0]
        assert r["last_seen_at"] > first[r["url"]][1]


def test_failing_source_logged_others_continue(conn):
    from hireember.discovery.companies import discover_companies
    from hireember.runs import execute_run, get_run_log

    add_three(conn)
    adapters, seen = make_adapters(ROLES, failing=("Beta",))
    box = {}

    def discover(c, run_id):
        box["result"] = discover_companies(c, adapters=adapters, run_id=run_id)
        return box["result"]

    stages = Recorder().stages()
    stages.discover = discover
    summary = execute_run("manual", stages=stages, conn=conn)
    assert sorted(seen) == ["Alpha", "Beta", "Gamma"]
    assert summary.found == 4 and len(run_rows(conn)) == 1
    assert box["result"]["failures"][0]["source"] == "Beta"
    assert "Beta is down" in box["result"]["failures"][0]["error"]
    log = get_run_log(conn, summary.id)
    assert any(e["source"] == "Beta" and "Beta is down" in e["message"] for e in log)
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 4


def test_all_sources_fail_run_still_ends(conn):
    from hireember.discovery.companies import discover_companies
    from hireember.runs import execute_run, get_run_log

    add_three(conn)
    adapters, _ = make_adapters(ROLES, failing=("Alpha", "Beta", "Gamma"))
    stages = Recorder().stages()
    stages.discover = lambda c, run_id: discover_companies(c, adapters=adapters, run_id=run_id)
    summary = execute_run("manual", stages=stages, conn=conn)
    assert summary.found == 0 and len(run_rows(conn)) == 1
    assert {e["source"] for e in get_run_log(conn, summary.id)} >= {"Alpha", "Beta", "Gamma"}


def test_empty_list_message(conn):
    from hireember.discovery.companies import discover_companies

    adapters, seen = make_adapters(ROLES)
    result = discover_companies(conn, adapters=adapters)
    assert result["found"] == 0 and result["message"] == EMPTY_MESSAGE and seen == []


def test_next_run_searches_added_and_skips_removed(conn):
    from hireember.companies import add_company, remove_company
    from hireember.discovery.companies import discover_companies

    add_company(conn, "Alpha", "https://alpha.example/careers", "workday")
    adapters, seen = make_adapters(ROLES)
    discover_companies(conn, adapters=adapters)
    assert seen == ["Alpha"]
    add_company(conn, "Beta", "https://beta.example/careers", "careers-page")
    seen.clear()
    discover_companies(conn, adapters=adapters)
    assert sorted(seen) == ["Alpha", "Beta"]
    remove_company(conn, "Alpha")
    seen.clear()
    discover_companies(conn, adapters=adapters)
    assert seen == ["Beta"]


def test_store_jobs_now_parameter_is_optional(conn):
    from hireember.database import store_jobs

    jobs = [{"url": "https://t.example/1", "title": "T", "location": "X"}]
    assert store_jobs(conn, jobs, "Site", "test", now="2026-01-01T00:00:00+00:00") == (1, 0)
    assert conn.execute("SELECT discovered_at FROM jobs").fetchone()[0] == "2026-01-01T00:00:00+00:00"
    assert store_jobs(conn, jobs, "Site", "test", now="2026-01-02T00:00:00+00:00") == (0, 1)
    row = conn.execute("SELECT discovered_at, last_seen_at FROM jobs").fetchone()
    assert row[0] == "2026-01-01T00:00:00+00:00" and row[1] == "2026-01-02T00:00:00+00:00"
    assert store_jobs(conn, [{"url": "https://t.example/2", "title": "U"}], "Site", "test") == (1, 0)


# -- CLI ---------------------------------------------------------------------

def invoke(*args):
    from hireember.cli import app

    return CliRunner().invoke(app, list(args))


def flat(result):
    return " ".join(result.output.split())


def test_cli_company_add_list_remove(isolated_db):
    r = invoke("company", "add", "Acme Corp", "--url", "https://acme.example/careers", "--ats", "workday")
    assert r.exit_code == 0, r.output
    assert 'Added company "Acme Corp".' in flat(r)
    r = invoke("company", "list")
    assert r.exit_code == 0
    out = flat(r)
    for text in ("Careers URL", "ATS", "Manual-only", "Acme Corp", "workday"):
        assert text in out
    assert "acme.example/careers" in out
    r = invoke("company", "add", "acme corp", "--url", "https://x.example", "--ats", "workday")
    assert r.exit_code == 1 and 'Company "acme corp" already exists.' in flat(r)
    r = invoke("company", "add", "Zed", "--url", "https://z.example", "--ats", "taleo")
    assert r.exit_code == 1
    assert 'Unknown ATS type "taleo". Valid types: workday, careers-page.' in flat(r)
    r = invoke("company", "remove", "Acme Corp")
    assert r.exit_code == 0 and 'Removed company "Acme Corp".' in flat(r)
    r = invoke("company", "remove", "Acme Corp")
    assert r.exit_code == 1 and 'Company "Acme Corp" not found.' in flat(r)
    r = invoke("company", "list")
    assert "No companies yet." in flat(r)
