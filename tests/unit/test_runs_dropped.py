import sqlite3

from hireember.migration import _PHASE5_RUN_COLUMNS
from hireember.runs import _stage_result
from hireember.web.queries import _dropped_text


def test_columns_registered():
    names = [n for n, _ in _PHASE5_RUN_COLUMNS]
    assert "dropped_title" in names and "dropped_location" in names


def test_dropped_text():
    assert _dropped_text({"dropped_title": 21, "dropped_location": 13}) == "Dropped 34 (21 title, 13 location)"
    assert _dropped_text({"dropped_title": 0, "dropped_location": 0}) == ""
    assert _dropped_text({}) == ""


def test_stage_result_appends_hint_only_with_drops():
    r = _stage_result("discover", {"found": 3, "new": 1, "dropped": {"title": 1, "location": 0}, "hint": "H."})
    assert r.message == "discover: 3 roles found, 1 new. H."
    r = _stage_result("discover", {"found": 3, "new": 1, "dropped": {"title": 0, "location": 0}, "hint": ""})
    assert r.message == "discover: 3 roles found, 1 new."


def test_migration_adds_columns_to_old_db(isolated_db):
    from hireember.database import init_db
    conn = init_db(isolated_db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    assert {"dropped_title", "dropped_location"} <= cols
    assert isinstance(conn, sqlite3.Connection)
