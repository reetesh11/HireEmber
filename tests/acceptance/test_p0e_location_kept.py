"""AC-8, AC-9 (unchanged side): acceptable locations are still scored for every source."""


import pytest
from p0e_helpers import FakeClient
from rich.console import Console

import hireember.cli as cli
from hireember import config, gating
from hireember.database import close_connection, init_db, store_jobs
from hireember.resumes import add_resume

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
SOURCES = [("indeed", "jobspy"), ("Workday TD", "workday_api"), ("Acme Careers", "json_ld")]
SENTENCE = "A job whose location is incompatible with the candidate's target locations is a reason for a low score."


@pytest.fixture
def env(tmp_path, isolated_db, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "absent-searches.yaml")
    monkeypatch.setattr(cli, "console", Console(width=300))
    monkeypatch.setenv("COLUMNS", "300")
    conn = init_db(isolated_db)
    config.ensure_dirs()
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    add_resume(conn, f, "Base", "python")
    client = FakeClient("SCORE: 9\nKEYWORDS: a\nREASONING: Great.")
    monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: client)
    yield conn, client
    close_connection(isolated_db)


def _add(conn, url, location, site="indeed", strategy="jobspy"):
    store_jobs(conn, [{"url": url, "title": "Python Dev", "company": "Acme", "location": location}], site, strategy)
    conn.execute("UPDATE jobs SET full_description = 'desc' WHERE url = ?", (url,))
    conn.commit()


@pytest.mark.parametrize("site, strategy", SOURCES, ids=["jobspy", "workday", "smart-extract"])
@pytest.mark.parametrize("location", ["Toronto, ON, Canada", "Vancouver, BC, Canada", "", None, "N/A"])
def test_ac8_ac9_acceptable_locations_are_scored(env, site, strategy, location):
    conn, client = env
    _add(conn, "https://j/2", location, site, strategy)
    result = gating.score_job_for_ticket(conn, "https://j/2", profile=PROFILE)
    assert client.calls == 1
    assert result.score == 9 and result.status == "pending"
