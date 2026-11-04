"""Phase 9 AC-5: dropped counts and hint in the discover result, the run log (max 20 titles) and the Runs tab."""

import pytest

from p9_helpers import FILTER_CFG, Client, Recorder, start_server, stop_server, use_config, utc


@pytest.fixture
def conn(isolated_db, tmp_path, monkeypatch):
    from hireember.database import init_db

    use_config(tmp_path, monkeypatch, searches=FILTER_CFG, profile={"personal": {}})
    return init_db()


def test_drop_tally_summary_and_hint():
    from hireember.intake import DropTally

    t = DropTally()
    assert t.counts == {"title": 0, "location": 0} and t.total == 0 and t.hint() == ""
    for i in range(21):
        t.add(f"T{i}", "title: sales")
    for i in range(13):
        t.add(f"L{i}", f"location: Austin {i}")
    assert t.total == 34 and t.counts == {"title": 21, "location": 13}
    assert t.items[0] == ("T0", "title: sales")
    assert t.summary_line() == "Dropped 34: 21 title, 13 location"
    assert t.hint() == "Dropped 34: 21 title, 13 location. Review them in Tickets (skipped) or edit rules in Profile."
    assert t.hint(kept=0).endswith(" Check your target roles and locations in Profile.")


def test_run_log_lists_at_most_20_titles(conn):
    from hireember.intake import DropTally, write_run_log
    from hireember.runs import get_run_log

    cur = conn.execute("INSERT INTO runs (kind, \"trigger\", status, started_at) "
                       "VALUES ('full', 'manual', 'running', '2026-03-01T00:00:00')")
    run_id = cur.lastrowid
    t = DropTally()
    for i in range(25):
        t.add(f"Sales Rep {i}", "title: sales")
    write_run_log(conn, run_id, t)
    messages = [e["message"] for e in get_run_log(conn, run_id)]
    assert messages[0] == "Dropped 25: 25 title, 0 location"
    assert sum(m.startswith("dropped: ") for m in messages) == 20
    assert "dropped: Sales Rep 0 (title: sales)" in messages
    assert "...and 5 more" in messages


def test_run_log_noop_when_nothing_dropped(conn):
    from hireember.intake import DropTally, write_run_log
    from hireember.runs import get_run_log

    write_run_log(conn, 1, DropTally())
    write_run_log(conn, None, DropTally())
    assert get_run_log(conn, 1) == []


def test_discover_result_has_dropped_and_hint(conn):
    from hireember.companies import add_company
    from hireember.discovery.companies import discover_companies

    add_company(conn, "Alpha", "https://alpha.example/careers", "workday")
    roles = [{"title": "Sales Lead", "url": "https://a.example/1", "location": "Berlin"},
             {"title": "Backend Engineer", "url": "https://a.example/2", "location": "Austin, TX"}]
    result = discover_companies(conn, adapters={"workday": lambda c: [dict(r) for r in roles]},
                                now=utc(2026, 3, 1))
    assert result["dropped"] == {"title": 1, "location": 1}
    assert result["new"] == 0
    assert result["hint"] == ("Dropped 2: 1 title, 1 location. Review them in Tickets (skipped) or edit "
                              "rules in Profile. Check your target roles and locations in Profile.")


def test_discover_result_zero_drops(conn):
    from hireember.companies import add_company
    from hireember.discovery.companies import discover_companies

    add_company(conn, "Alpha", "https://alpha.example/careers", "workday")
    roles = [{"title": "Backend Engineer", "url": "https://a.example/2", "location": "Berlin"}]
    result = discover_companies(conn, adapters={"workday": lambda c: [dict(r) for r in roles]})
    assert result["dropped"] == {"title": 0, "location": 0} and result["hint"] == "" and result["new"] == 1


def test_runs_tab_shows_dropped_counts(conn, isolated_db):
    from hireember.runs import execute_run

    rec = Recorder()
    rec.results["discover"] = {"found": 40, "new": 6, "dropped": {"title": 21, "location": 13},
                               "hint": "Dropped 34: 21 title, 13 location. Review them in Tickets (skipped) "
                                       "or edit rules in Profile."}
    summary = execute_run("manual", stages=rec.stages(), conn=conn)
    assert summary.dropped_title == 21 and summary.dropped_location == 13
    server, thread = start_server(isolated_db)
    try:
        client = Client(server.server_address[1])
        for path in ("/runs?fragment=1", "/runs"):
            status, _, payload = client.request("GET", path)
            html = payload.decode("utf-8")
            assert status == 200
            assert ">Dropped<" in html
            assert "Dropped 34 (21 title, 13 location)" in html
    finally:
        stop_server(server, thread)
