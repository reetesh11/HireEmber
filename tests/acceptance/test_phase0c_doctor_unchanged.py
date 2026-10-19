"""Phase 0c: behaviour that must not change."""

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


# -- AC-7 (unchanged) ---------------------------------------------------------

def test_ac7_resolve_jobspy_sites_none_and_list(caplog):
    from hireember.config import DEFAULT_JOBSPY_SITES, resolve_jobspy_sites

    assert resolve_jobspy_sites(None) == list(DEFAULT_JOBSPY_SITES)
    with caplog.at_level("WARNING"):
        assert resolve_jobspy_sites(["indeed", "LinkedIn"]) == ["indeed"]
    assert any("linkedin" in r.getMessage().lower() for r in caplog.records)


def test_ac7_valid_configs_unchanged(searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text("sites: [indeed, zip_recruiter]\n", encoding="utf-8")
    (config_dir / "employers.yaml").write_text("", encoding="utf-8")
    (config_dir / "sites.yaml").write_text("", encoding="utf-8")
    check = check_sources()
    assert check.status == "OK"
    assert check.note == "JobSpy: indeed, zip_recruiter | Workday employers: 0 | career sites: 0"


def test_ac7_resolve_app_dir_unchanged(tmp_path):
    from hireember.config import resolve_app_dir

    assert resolve_app_dir(environ={"HIREEMBER_DIR": str(tmp_path / "x")}, home=tmp_path)[0] == tmp_path / "x"
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)
    (tmp_path / ".hireember").mkdir()
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)
