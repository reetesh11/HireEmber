"""Rename AC-12 (gate-1 scope addition): doctor reports malformed source YAML as MISSING, never crashes."""

import re
import shutil

import pytest
from typer.testing import CliRunner

STATUS_WORDS = ("OK", "MISSING", "WARN", "optional")


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """A writable copy of the package config/ folder, wired in as hireember.config.CONFIG_DIR."""
    import hireember.config

    copy = tmp_path / "pkg-config"
    shutil.copytree(hireember.config.CONFIG_DIR, copy)
    monkeypatch.setattr(hireember.config, "CONFIG_DIR", copy)
    return copy


@pytest.fixture
def searches(tmp_path, monkeypatch):
    """Point hireember.config.SEARCH_CONFIG_PATH at a temp searches.yaml; return its path."""
    import hireember.config

    path = tmp_path / "searches.yaml"
    monkeypatch.setattr(hireember.config, "SEARCH_CONFIG_PATH", path)
    return path


def _assert_missing(check, label: str, contains: str | None = None):
    assert check.name == "Job sources"
    assert check.status == "MISSING", check
    assert check.note.startswith(label + ": "), check.note
    if contains:
        assert contains in check.note, check.note


@pytest.mark.parametrize(
    "content, contains",
    [("sites: [indeed\n", None), ("- indeed\n", "mapping"), ("just a string\n", "mapping")],
    ids=["yaml-error", "top-level-list", "top-level-scalar"],
)
def test_bad_user_searches_yaml_reports_missing(content, contains, searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text(content, encoding="utf-8")
    _assert_missing(check_sources(), "searches.yaml", contains)


def test_bad_example_searches_yaml_reports_missing(searches, config_dir):
    from hireember.doctor import check_sources

    assert not searches.exists()
    (config_dir / "searches.example.yaml").write_text("boards: [indeed\n", encoding="utf-8")
    _assert_missing(check_sources(), "searches.example.yaml")


def test_non_dict_search_cfg_argument_reports_missing(config_dir):
    from hireember.doctor import check_sources

    _assert_missing(check_sources(["indeed"]), "searches.yaml", "mapping")


@pytest.mark.parametrize("name", ["employers.yaml", "sites.yaml"])
@pytest.mark.parametrize(
    "content, contains",
    [("key: [unclosed\n", None), ("- a\n- b\n", "mapping")],
    ids=["yaml-error", "top-level-list"],
)
def test_bad_package_registry_reports_missing(name, content, contains, searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text("sites: [indeed]\n", encoding="utf-8")
    (config_dir / name).write_text(content, encoding="utf-8")
    _assert_missing(check_sources(), name, contains)


def test_unreadable_searches_yaml_reports_missing(searches, config_dir):
    from hireember.doctor import check_sources

    searches.mkdir()  # exists, but reading it raises an OSError
    _assert_missing(check_sources(), "searches.yaml")


def test_empty_files_count_as_empty_and_valid_configs_stay_ok(searches, config_dir):
    from hireember.doctor import check_sources

    searches.write_text("", encoding="utf-8")
    (config_dir / "employers.yaml").write_text("", encoding="utf-8")
    (config_dir / "sites.yaml").write_text("", encoding="utf-8")
    check = check_sources()
    assert check.name == "Job sources"
    assert check.note == "JobSpy: indeed, zip_recruiter | Workday employers: 0 | career sites: 0"
    assert check.status == "OK"

    (config_dir / "employers.yaml").write_text(
        "employers:\n  acme:\n    name: Acme\n    tenant: acme\n    site_id: External\n"
        "    base_url: https://acme.wd1.myworkdayjobs.com\n",
        encoding="utf-8",
    )
    (config_dir / "sites.yaml").write_text(
        "sites:\n  - name: Acme Careers\n    url: https://acme.example/jobs?q={query_encoded}\n"
        "    type: search\n",
        encoding="utf-8",
    )
    check = check_sources({"sites": ["glassdoor", "linkedin"]})
    assert check.status == "OK"
    assert check.note == "JobSpy: glassdoor | Workday employers: 1 | career sites: 1"


def _job_sources_status(output: str) -> str | None:
    pattern = re.compile(r"^\s+Job sources\s+(" + "|".join(STATUS_WORDS) + r")\b")
    for line in output.splitlines():
        m = pattern.match(line)
        if m:
            return m.group(1)
    return None


@pytest.mark.parametrize("content", ["sites: [indeed\n", "- indeed\n"], ids=["yaml-error", "top-level-list"])
def test_run_checks_and_cli_doctor_complete_with_bad_searches_yaml(content, searches, isolated_db):
    from hireember.cli import app
    from hireember.doctor import run_checks

    searches.write_text(content, encoding="utf-8")

    sources = [c for c in run_checks() if c.name == "Job sources"]
    assert len(sources) == 1 and sources[0].status == "MISSING", sources

    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert _job_sources_status(result.output) == "MISSING", result.output
