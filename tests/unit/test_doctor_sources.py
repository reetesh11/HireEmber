"""Unit tests for doctor.check_sources with malformed source YAML."""

import pytest

from hireember import config, doctor

VALID_SITES = "sites:\n  - name: Acme\n    url: https://acme.example/jobs\n    type: search\n"


@pytest.fixture
def pkg_config(tmp_path, monkeypatch):
    """An empty CONFIG_DIR with a valid sites.yaml, plus a temp SEARCH_CONFIG_PATH."""
    cfg = tmp_path / "pkg"
    cfg.mkdir()
    (cfg / "sites.yaml").write_text(VALID_SITES, encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_DIR", cfg)
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "searches.yaml")
    return cfg


@pytest.mark.parametrize("content", ["sites: [indeed\n", "- indeed\n"])
def test_bad_searches_yaml_is_missing(pkg_config, content):
    config.SEARCH_CONFIG_PATH.write_text(content, encoding="utf-8")
    check = doctor.check_sources()
    assert check.status == "MISSING"
    assert check.note.startswith("searches.yaml: ")
    assert "\n" not in check.note


def test_broken_employers_yaml_is_missing(pkg_config):
    config.SEARCH_CONFIG_PATH.write_text("sites: [indeed]\n", encoding="utf-8")
    (pkg_config / "employers.yaml").write_text("employers: {acme\n", encoding="utf-8")
    check = doctor.check_sources()
    assert check.status == "MISSING"
    assert check.note.startswith("employers.yaml: ")


def test_list_valued_sites_yaml_is_missing(pkg_config):
    config.SEARCH_CONFIG_PATH.write_text("sites: [indeed]\n", encoding="utf-8")
    (pkg_config / "sites.yaml").write_text("- a\n", encoding="utf-8")
    check = doctor.check_sources()
    assert check.status == "MISSING"
    assert check.note.startswith("sites.yaml: ")
    assert "mapping" in check.note


def test_empty_employers_yaml_counts_as_zero(pkg_config):
    config.SEARCH_CONFIG_PATH.write_text("sites: [indeed]\n", encoding="utf-8")
    (pkg_config / "employers.yaml").write_text("", encoding="utf-8")
    check = doctor.check_sources()
    assert check.status == "OK"
    assert check.note == "JobSpy: indeed | Workday employers: 0 | career sites: 1"


def test_non_dict_search_cfg_is_missing(pkg_config):
    check = doctor.check_sources("indeed")
    assert check.status == "MISSING"
    assert check.note == "searches.yaml: top level must be a mapping, got str"


def test_run_checks_survives_broken_searches_yaml(pkg_config, isolated_db):
    config.SEARCH_CONFIG_PATH.write_text("sites: [indeed\n", encoding="utf-8")
    checks = doctor.run_checks()
    assert len(checks) == 12
    sources = [c for c in checks if c.name == "Job sources"]
    assert sources[0].status == "MISSING"
