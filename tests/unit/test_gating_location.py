import pytest

from hireember import config, gating, tickets
from hireember.database import close_connection, init_db, store_jobs
from hireember.resumes import add_resume

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}


class Client:
    calls = 0

    def chat(self, messages, **kwargs):
        Client.calls += 1
        return "SCORE: 9\nKEYWORDS: a\nREASONING: Great."


@pytest.fixture
def conn(tmp_path, isolated_db, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "absent.yaml")
    Client.calls = 0
    monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: Client())
    c = init_db(isolated_db)
    config.ensure_dirs()
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    add_resume(c, f, "Base", "python")
    yield c
    close_connection(isolated_db)


def _add(conn, url, location, site, strategy):
    store_jobs(conn, [{"url": url, "title": "Dev", "company": "Acme", "location": location}], site, strategy)
    conn.execute("UPDATE jobs SET full_description = 'd' WHERE url = ?", (url,))
    conn.commit()


@pytest.mark.parametrize("site, strategy", [("indeed", "jobspy"), ("Workday X", "workday_api"), ("Acme", "json_ld")])
def test_skipped_without_llm_call(conn, site, strategy):
    _add(conn, "u1", "Berlin, Germany", site, strategy)
    result = gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    assert (result.status, result.reason, result.score) == ("skipped", "location: Berlin, Germany", None)
    assert Client.calls == 0


def test_scored_job_is_not_reskipped(conn):
    _add(conn, "u1", "Berlin, Germany", "indeed", "jobspy")
    tickets.open_ticket(conn, "u1")
    tickets.set_job_score(conn, "u1", 8, "earlier")
    result = gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    assert not result.reason.startswith("location:")
    assert Client.calls == 1


def test_repeat_run_keeps_one_ticket_event(conn):
    _add(conn, "u1", "Berlin, Germany", "indeed", "jobspy")
    first = gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    n = conn.execute("SELECT COUNT(*) FROM ticket_events WHERE ticket_id = ?", (first.ticket_id,)).fetchone()[0]
    assert n == 1
