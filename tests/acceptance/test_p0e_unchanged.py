"""AC-14: behaviour that must not change (green before and after)."""

import sys
import types

import pytest
from p0e_helpers import FakeClient

from hireember import config, gating, tickets
from hireember.database import close_connection, init_db, store_jobs
from hireember.resumes import add_resume


def test_llm_client_and_detect_provider_signatures_unchanged(monkeypatch):
    from hireember import llm

    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    assert llm._detect_provider() == ("https://api.openai.com/v1", "gpt-4o-mini", "oa")
    c = llm.LLMClient("http://localhost:1/v1", "m", "")
    assert (c.base_url, c.model, c.api_key) == ("http://localhost:1/v1", "m", "")
    c.close()
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(RuntimeError):
        llm._detect_provider()


def test_scored_job_outside_location_is_not_retroactively_skipped(tmp_path, isolated_db, monkeypatch):
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "absent.yaml")
    conn = init_db(isolated_db)
    config.ensure_dirs()
    store_jobs(conn, [{"url": "u1", "title": "Python Dev", "company": "Acme", "location": "Berlin, Germany"}], "S", "t")
    conn.execute("UPDATE jobs SET full_description = 'desc'")
    conn.commit()
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    add_resume(conn, f, "Base", "python")
    tickets.open_ticket(conn, "u1")
    tickets.set_job_score(conn, "u1", 8, "earlier score")
    client = FakeClient("SCORE: 9\nKEYWORDS: a\nREASONING: Great.")
    monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: client)

    profile = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
    result = gating.score_job_for_ticket(conn, "u1", profile=profile)
    assert not (result.reason or "").startswith("location:")
    assert client.calls == 1
    close_connection(isolated_db)


def test_jobspy_check_ok(monkeypatch):
    from hireember import doctor

    monkeypatch.setitem(sys.modules, "jobspy", types.ModuleType("jobspy"))
    assert doctor._check_jobspy() == doctor.Check("python-jobspy", "OK", "Job board scraping available")
