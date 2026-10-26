"""Company discovery: Workday URL parsing and the careers-page adapter's error handling."""

import pytest

from hireember.discovery import companies as dc


def test_workday_employer_from_url():
    e = dc.workday_employer("https://acme.wd3.myworkdayjobs.com/en-US/Acme_Careers", "Acme")
    assert e == {"name": "Acme", "tenant": "acme", "site_id": "Acme_Careers",
                 "base_url": "https://acme.wd3.myworkdayjobs.com"}
    assert dc.workday_employer("https://x.wd1.myworkdayjobs.com/External", "X")["site_id"] == "External"


@pytest.mark.parametrize("url", ["https://example.com/jobs", "https://x.wd1.myworkdayjobs.com/"])
def test_workday_employer_rejects_other_urls(url):
    with pytest.raises(ValueError):
        dc.workday_employer(url, "X")


def test_careers_page_adapter_status_handling(monkeypatch):
    from hireember.discovery import smartextract

    company = {"name": "N", "careers_url": "https://n.example/careers"}
    monkeypatch.setattr(smartextract, "_run_one_site",
                        lambda n, u: {"status": "LLM_ERROR", "error": "no model"})
    with pytest.raises(RuntimeError, match="no model"):
        dc.careers_page_adapter(company)
    monkeypatch.setattr(smartextract, "_run_one_site",
                        lambda n, u: {"status": "PASS", "jobs": [{"title": "T", "url": "u"}]})
    assert dc.careers_page_adapter(company) == [{"title": "T", "url": "u"}]
    monkeypatch.setattr(smartextract, "_run_one_site", lambda n, u: {"status": "???"})
    with pytest.raises(RuntimeError):
        dc.careers_page_adapter(company)
