from pathlib import Path

from hireember.enrichment.page import looks_like_login, parse_job_page

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "jobpages"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def no_ai(url, text):
    raise AssertionError("the AI must not be called")


def test_jsonld_page():
    data = parse_job_page(load("jsonld.html"), "https://careers.acme.example/1", extract=no_ai)
    assert (data["title"], data["company"]) == ("Backend Engineer", "Acme Corp")
    assert data["location"] == "Berlin, DE"


def test_greenhouse_page_uses_site_name():
    data = parse_job_page(load("greenhouse.html"), "https://boards.greenhouse.io/acme/jobs/1", extract=no_ai)
    assert data["title"] == "Data Engineer" and data["company"] == "Gardenhouse"
    assert data["location"] == "Remote, Europe"


def test_lever_page_company_from_url_slug():
    data = parse_job_page(load("lever.html"), "https://jobs.lever.co/acme/2", extract=no_ai)
    assert data["company"] == "acme" and data["title"] == "Product Designer"


def test_unknown_layout_calls_extract_once():
    calls = []

    def extract(url, text):
        calls.append(text)
        return {"title": "Chef", "company": "", "location": "", "description": "Cook for us daily.",
                "application_url": ""}

    data = parse_job_page(load("unknown.html"), "https://example.com/x", extract=extract)
    assert len(calls) == 1 and "Cook for us." in calls[0]
    assert data["company"] == "example.com"


def test_login_and_notfound_bodies():
    assert looks_like_login(load("login.html"), "https://example.com/p")
    assert not looks_like_login(load("notfound.html"), "https://example.com/p")
    assert looks_like_login(load("notfound.html"), "https://example.com/login")
