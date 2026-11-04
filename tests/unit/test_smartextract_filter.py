import re
from pathlib import Path

import pytest

import hireember
from hireember import config
from hireember.database import close_connection, init_db
from hireember.discovery import smartextract
from hireember.intake import JobFilter

CFG = {"title_exclude": ["sales"], "title_include": ["engineer"], "location": {"accept_patterns": ["Berlin"]}}


@pytest.fixture
def conn(isolated_db):
    c = init_db(isolated_db)
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_careers_page_jobs_are_filtered(conn, monkeypatch):
    jobs = [{"url": "https://c/1", "title": "Engineer", "location": "Berlin"},
            {"url": "https://c/2", "title": "Sales Lead", "location": "Berlin"},
            {"url": "https://c/3", "title": "Engineer", "location": "Austin, TX"}]
    monkeypatch.setattr(smartextract, "_run_one_site",
                        lambda n, u: {"status": "PASS", "name": n, "jobs": jobs, "strategy": "json_ld",
                                      "total": 3, "titles": 3})
    result = smartextract._run_all([{"name": "Acme", "url": "u"}], flt=JobFilter.load(CFG, {}))
    assert result["total_new"] == 1 and result["dropped"] == {"title": 1, "location": 1}
    assert result["hint"].startswith("Dropped 2: 1 title, 1 location.")


def test_only_one_location_matcher_in_discovery():
    root = Path(hireember.__file__).parent / "discovery"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "_location_ok" not in text, path
        assert not re.search(r"def\s+_?location_(ok|match)\w*", text), path
