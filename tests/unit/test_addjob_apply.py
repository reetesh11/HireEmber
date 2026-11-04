import pytest

from hireember import addjob, tickets
from hireember.addjob import AddRow


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db(isolated_db)
    yield c
    close_connection(isolated_db)


def added_row(conn, name):
    from hireember.database import store_jobs

    url = f"https://a.example/{name}"
    store_jobs(conn, [{"url": url, "title": name}], "a.example", "manual")
    tid = tickets.open_ticket(conn, url, "pending", "added by link")
    return AddRow(url, "added", tid, None, "", addjob.STOPPED_NO_APPLY)


def test_blocked_added_job_is_not_launched(conn, monkeypatch):
    row = added_row(conn, "b")
    tickets.set_status(conn, row.ticket_id, "blocked for human", reason="no base resume")
    calls = []
    monkeypatch.setattr("hireember.apply.launcher.main", lambda **kw: calls.append(kw))
    monkeypatch.setattr("hireember.preflight.run_preflight", lambda *a, **k: calls.append("pre"))
    addjob.apply_added(conn, [row], review=True)
    assert calls == []


def test_launcher_error_is_isolated(conn, monkeypatch):
    rows = [added_row(conn, "x"), added_row(conn, "y")]
    seen = []

    def main(**kw):
        seen.append(kw["target_url"])
        raise RuntimeError("browser died")

    class Outcome:
        proceed = True

    monkeypatch.setattr("hireember.apply.launcher.main", main)
    monkeypatch.setattr("hireember.preflight.run_preflight", lambda *a, **k: Outcome())
    addjob.apply_added(conn, rows, review=True)
    assert len(seen) == 2 and all(r.next_step == "Waiting at review" for r in rows)
