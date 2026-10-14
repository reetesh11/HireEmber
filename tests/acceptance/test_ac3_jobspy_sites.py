"""AC-3: default JobSpy site lists never include LinkedIn."""

from pathlib import Path

import pandas as pd
import pytest
import yaml

EXAMPLE_SEARCHES = (
    Path(__file__).resolve().parents[2] / "src" / "applypilot" / "config" / "searches.example.yaml"
)


@pytest.fixture
def scrape_calls(monkeypatch, isolated_db):
    """Stub JobSpy's scrape_jobs; record every call's kwargs; return no rows."""
    import applypilot.discovery.jobspy as jobspy_mod

    calls: list[dict] = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(jobspy_mod, "scrape_jobs", fake_scrape_jobs)
    return calls


def _lower(sites):
    return [str(s).strip().lower() for s in sites]


def test_search_jobs_default_sites_exclude_linkedin(scrape_calls):
    from applypilot.discovery.jobspy import search_jobs

    result = search_jobs("python developer", "Remote", sites=None)

    assert len(scrape_calls) == 1
    kwargs = scrape_calls[0]
    assert "linkedin" not in _lower(kwargs["site_name"])
    assert list(kwargs["site_name"]) == ["indeed", "zip_recruiter"]
    assert "linkedin_fetch_description" not in kwargs
    assert result["total"] == 0


def test_full_crawl_default_sites_exclude_linkedin(scrape_calls):
    from applypilot.discovery.jobspy import _full_crawl

    search_cfg = {
        "queries": [{"query": "python developer", "tier": 1}],
        "locations": [{"location": "Remote", "remote": True}],
    }
    _full_crawl(search_cfg, sites=None, max_retries=0)

    assert scrape_calls, "scrape_jobs was never called"
    seen: list[str] = []
    for kwargs in scrape_calls:
        names = _lower(kwargs["site_name"])
        assert "linkedin" not in names
        assert "linkedin_fetch_description" not in kwargs
        seen.extend(names)
    assert sorted(seen) == ["indeed", "zip_recruiter"]


def test_search_jobs_drops_explicitly_configured_linkedin(scrape_calls):
    from applypilot.discovery.jobspy import search_jobs

    search_jobs("python developer", "Remote", sites=["indeed", "LinkedIn", " linkedin ", "zip_recruiter"])

    assert len(scrape_calls) == 1
    assert list(scrape_calls[0]["site_name"]) == ["indeed", "zip_recruiter"]
    assert "linkedin_fetch_description" not in scrape_calls[0]


def test_example_search_config_boards_exclude_linkedin():
    cfg = yaml.safe_load(EXAMPLE_SEARCHES.read_text(encoding="utf-8"))
    boards = _lower(cfg.get("boards") or [])
    assert "linkedin" not in boards
    for kept in ("indeed", "glassdoor", "zip_recruiter", "google"):
        assert kept in boards

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, str):
            yield node

    assert not [v for v in walk(cfg) if v.strip().lower() == "linkedin"]
