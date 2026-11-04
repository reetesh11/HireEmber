import io

import yaml
from rich.console import Console

from hireember import config
from hireember.wizard import init as wiz


def _run(tmp_path, monkeypatch, existing=None, resume="Software engineer"):
    sp = tmp_path / "searches.yaml"
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", sp)
    monkeypatch.setattr(wiz, "SEARCH_CONFIG_PATH", sp)
    monkeypatch.setattr(config, "PROFILE_PATH", tmp_path / "profile.json")
    rp = tmp_path / "resume.txt"
    rp.write_text(resume)
    monkeypatch.setattr(config, "RESUME_PATH", rp)
    if existing:
        sp.write_text(yaml.safe_dump(existing))
    buf = io.StringIO()
    wiz._setup_searches(lambda q, **k: "Remote" if "location" in q.lower() else "Nurse, Backend Engineer",
                        Console(file=buf, width=200))
    return yaml.safe_load(sp.read_text()), buf.getvalue()


def test_lists_written_and_message(tmp_path, monkeypatch):
    cfg, out = _run(tmp_path, monkeypatch)
    assert "nurse" in cfg["title_include"] and "sales" in cfg["title_exclude"]
    assert "Edit them in the dashboard Profile tab." in out


def test_software_role_detected_from_roles(tmp_path, monkeypatch):
    cfg, _ = _run(tmp_path, monkeypatch, resume="Ward care")
    assert "backend engineer" in cfg["title_include"]  # role itself is software-ish


def test_existing_lists_kept(tmp_path, monkeypatch):
    cfg, _ = _run(tmp_path, monkeypatch, existing={"title_include": ["x"], "exclude_titles": ["y"]})
    assert cfg["title_include"] == ["x"] and cfg["title_exclude"] == ["y"]
