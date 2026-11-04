"""Phase 9 AC-7: hireember init writes title_include / title_exclude proposed from the resume and profile."""

import io

import yaml
from rich.console import Console

from p9_helpers import use_config


def run_setup(tmp_path, monkeypatch, existing=None):
    from hireember import config
    from hireember.wizard import init as wiz

    use_config(tmp_path, monkeypatch, searches=existing,
               profile={"personal": {"city": "Berlin"}, "experience": {"target_role": "Software Engineer"}})
    resume = tmp_path / "resume.txt"
    resume.write_text("Jane Doe\nSoftware engineer with Python and SQL.\n", encoding="utf-8")
    monkeypatch.setattr(config, "RESUME_PATH", resume)
    if hasattr(wiz, "RESUME_PATH"):
        monkeypatch.setattr(wiz, "RESUME_PATH", resume)

    def ask(question, **kwargs):
        if "location" in question.lower() and "radius" not in question.lower():
            return "Berlin"
        if "radius" in question.lower():
            return "0"
        return "Backend Engineer, Full Stack Developer"

    buf = io.StringIO()
    wiz._setup_searches(ask, Console(file=buf, width=200))
    return yaml.safe_load(config.SEARCH_CONFIG_PATH.read_text(encoding="utf-8")), buf.getvalue()


def test_init_writes_proposed_lists(tmp_path, monkeypatch):
    cfg, out = run_setup(tmp_path, monkeypatch)
    assert cfg["title_include"] and cfg["title_exclude"]
    assert "sales" in cfg["title_exclude"] and "program manager" in cfg["title_exclude"]
    assert "backend engineer" in cfg["title_include"]
    assert [q["query"] for q in cfg["queries"]] == ["Backend Engineer", "Full Stack Developer"]
    assert "Proposed target roles and hard-no titles. Edit them in the dashboard Profile tab." in out


def test_existing_non_empty_lists_are_kept(tmp_path, monkeypatch):
    cfg, _ = run_setup(tmp_path, monkeypatch,
                       existing={"title_include": ["data scientist"], "exclude_titles": ["intern"]})
    assert cfg["title_include"] == ["data scientist"]
    assert cfg.get("title_exclude", cfg.get("exclude_titles")) == ["intern"]
