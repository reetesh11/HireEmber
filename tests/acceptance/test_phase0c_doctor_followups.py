"""Phase 0c: doctor source-check hardening, resolve_jobspy_sites validation, app dir, docs."""

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    import hireember.config

    copy = tmp_path / "pkg-config"
    shutil.copytree(hireember.config.CONFIG_DIR, copy)
    monkeypatch.setattr(hireember.config, "CONFIG_DIR", copy)
    return copy


@pytest.fixture
def searches(tmp_path, monkeypatch):
    import hireember.config

    path = tmp_path / "searches.yaml"
    monkeypatch.setattr(hireember.config, "SEARCH_CONFIG_PATH", path)
    return path


# -- AC-2 ---------------------------------------------------------------------

@pytest.mark.parametrize("value", ["5", "indeed", "{a: 1}"], ids=["int", "string", "mapping"])
def test_ac2_bad_searches_sites_reports_missing(value, searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text(f"sites: {value}\n", encoding="utf-8")
    check = check_sources()
    assert check.name == "Job sources"
    assert check.status == "MISSING", check
    assert check.note.startswith("searches.yaml:"), check.note
    assert "must be a list" in check.note
    assert "i, n" not in check.note and "'i'" not in check.note


def test_ac2_non_string_items_report_missing(config_dir):
    from hireember.doctor import check_sources

    check = check_sources({"sites": ["indeed", 5]})
    assert check.status == "MISSING", check
    assert check.note.startswith("searches.yaml:"), check.note


# -- AC-3 ---------------------------------------------------------------------

def test_ac3_employers_not_mapping(searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text("sites: [indeed]\n", encoding="utf-8")
    (config_dir / "employers.yaml").write_text("employers: 5\n", encoding="utf-8")
    check = check_sources()
    assert check.status == "MISSING", check
    assert check.note.startswith("employers.yaml:"), check.note


@pytest.mark.parametrize("value", ["5", "indeed"], ids=["int", "string"])
def test_ac3_sites_yaml_not_list(value, searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text("sites: [indeed]\n", encoding="utf-8")
    (config_dir / "sites.yaml").write_text(f"sites: {value}\n", encoding="utf-8")
    check = check_sources()
    assert check.status == "MISSING", check
    assert check.note.startswith("sites.yaml:"), check.note
    assert "must be a list" in check.note


# -- AC-4 ---------------------------------------------------------------------

@pytest.mark.parametrize("value", ["indeed", 5, {"a": 1}], ids=["str", "int", "dict"])
def test_ac4_resolve_jobspy_sites_rejects_non_list(value):
    from hireember.config import resolve_jobspy_sites

    with pytest.raises(ValueError, match="list"):
        resolve_jobspy_sites(value)


def test_ac4_search_jobs_reports_error(isolated_db):
    from hireember.discovery.jobspy import search_jobs

    res = search_jobs("python", "Remote", sites="indeed")
    assert "list" in res["error"]
    assert (res["total"], res["new"], res["existing"]) == (0, 0, 0)


def test_ac4_full_crawl_reports_error(isolated_db):
    from hireember.discovery.jobspy import _full_crawl

    res = _full_crawl({"queries": [], "locations": []}, sites="indeed")
    assert "list" in res["error"]
    assert (res["new"], res["existing"], res["errors"], res["queries"]) == (0, 0, 0, 0)
    assert "db_total" in res


def test_ac4_run_discovery_does_not_raise(isolated_db):
    from hireember.discovery.jobspy import run_discovery

    res = run_discovery({"sites": "indeed", "queries": [], "locations": []})
    assert "list" in res["error"]


# -- AC-5 ---------------------------------------------------------------------

def test_ac5_stray_hireember_file_ignored(tmp_path):
    from hireember.config import resolve_app_dir

    (tmp_path / ".hireember").write_text("stray", encoding="utf-8")
    (tmp_path / ".applypilot").mkdir()
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".applypilot", True)


def test_ac5_legacy_notice_printed_with_stray_file(tmp_path):
    import os
    import subprocess
    import sys

    home = tmp_path / "home"
    home.mkdir()
    (home / ".hireember").write_text("stray", encoding="utf-8")
    (home / ".applypilot").mkdir()
    env = dict(os.environ)
    env.pop("HIREEMBER_DIR", None)
    env.pop("APPLYPILOT_DIR", None)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-c", "import hireember.config as c; print(c.USING_LEGACY_APP_DIR)"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "True"
    assert "legacy data folder" in proc.stderr


# -- AC-6 ---------------------------------------------------------------------

def test_ac6_readme_badge_points_at_hireember():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://pypi.org/project/hireember/" in text
    assert "img.shields.io/pypi/v/hireember" in text
    assert "applypilot" not in "\n".join(l for l in text.splitlines() if "pypi" in l)


def test_ac6_contributing_commands_exist():
    from hireember.cli import app

    text = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "hireember discover" not in text
    runner = CliRunner()
    top = runner.invoke(app, ["--help"]).output
    for m in re.finditer(r"(?<![\w/.-])hireember ([a-z][\w-]*)", text):
        sub = m.group(1)
        if sub in ("package",):
            continue
        assert re.search(rf"^\W*{re.escape(sub)}\b", top, re.M), f"unknown command: hireember {sub}"
    run_help = runner.invoke(app, ["run", "--help"]).output
    for m in re.finditer(r"hireember run ([a-z]+)", text):
        assert m.group(1) in run_help, m.group(0)
    assert "hireember run discover" in text
