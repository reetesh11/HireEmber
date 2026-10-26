"""Single-stage runner and the default stage wiring."""

import json

import pytest

from hireember import runs, stages


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_default_stages_map_results(conn, monkeypatch):
    from hireember.apply import launcher
    from hireember.scoring import scorer, tailor

    monkeypatch.setattr(tailor, "run_tailoring",
                        lambda **kw: {"approved": 3, "failed": 1, "errors": 2})
    monkeypatch.setattr(scorer, "run_scoring", lambda: {"scored": 4, "location_skipped": 2})
    monkeypatch.setattr(launcher, "main", lambda limit, headless: limit - 1)
    s = stages.default_stages()
    assert s.tailor(conn, None) == {"created": 3, "blocked": 3}
    assert s.score(conn, None) == {"scored": 4, "skipped": 2}
    assert s.apply(conn, None, 5) == {"submitted": 4}


def test_run_stage_failure_propagates_and_releases_lock(conn):
    def boom(c, rid):
        raise RuntimeError("nope")

    s = runs.Stages(discover=boom, enrich=boom, score=boom, tailor=boom, apply=boom)
    with pytest.raises(RuntimeError):
        runs.run_stage("score", stages=s, conn=conn)
    assert not runs.is_running(conn)


def test_async_failure_is_stored(conn):
    def boom(c, rid):
        raise RuntimeError("nope")

    s = runs.Stages(discover=boom, enrich=boom, score=boom, tailor=boom, apply=boom)
    runs.start_stage_async("tailor", stages=s, conn=conn).join(10)
    assert not runs.is_running(conn)
    stored = json.loads(conn.execute(
        "SELECT value FROM settings WHERE key = 'last_stage_result'").fetchone()[0])
    assert stored["stage"] == "tailor" and "nope" in stored["message"]
