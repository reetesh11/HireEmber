"""AC-6: `hireember doctor` reports Python, Chrome, Node, Claude Code, DB and sources."""

import re
import sqlite3

import pytest
from typer.testing import CliRunner

import hireember.config
from hireember.cli import app
from hireember.database import init_db

STATUS_WORDS = ("OK", "MISSING", "WARN", "optional")
CHECK_ORDER = [
    "Python",
    "profile.json",
    "resume.txt",
    "searches.yaml",
    "python-jobspy",
    "LLM API key",
    "Claude Code CLI",
    "Chrome/Chromium",
    "Node.js",
    "Database",
    "Job sources",
    "CapSolver API key",
]


def _no_chrome():
    raise FileNotFoundError("Chrome/Chromium not found (test)")


def _run_doctor() -> str:
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    return result.output


def _status_of(output: str, name: str) -> str | None:
    pattern = re.compile(r"^\s+" + re.escape(name) + r"\s+(" + "|".join(STATUS_WORDS) + r")\b")
    for line in output.splitlines():
        m = pattern.match(line)
        if m:
            return m.group(1)
    return None


def test_doctor_prints_a_status_line_for_each_required_check(isolated_db):
    output = _run_doctor()

    assert "HireEmber Doctor" in output
    for name in ("Python", "Chrome/Chromium", "Node.js", "Claude Code CLI", "Database", "Job sources"):
        assert _status_of(output, name) is not None, f"no status line for {name!r} in:\n{output}"


def test_run_checks_returns_all_checks_in_cli_order(isolated_db):
    from hireember.doctor import run_checks

    checks = run_checks()
    assert [c.name for c in checks] == CHECK_ORDER
    assert all(c.status in STATUS_WORDS for c in checks)


def test_chrome_hidden_reports_missing(monkeypatch, isolated_db):
    from hireember.doctor import check_chrome

    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(hireember.config, "get_chrome_path", _no_chrome)

    check = check_chrome()
    assert check.name == "Chrome/Chromium"
    assert check.status == "MISSING"
    assert "CHROME_PATH" in check.note
    assert _status_of(_run_doctor(), "Chrome/Chromium") == "MISSING"


def test_chrome_found_reports_ok(monkeypatch):
    from hireember.doctor import check_chrome

    monkeypatch.setattr(hireember.config, "get_chrome_path", lambda: "/opt/chrome/chrome")

    check = check_chrome()
    assert (check.name, check.status, check.note) == ("Chrome/Chromium", "OK", "/opt/chrome/chrome")


@pytest.mark.parametrize(
    "version, note_part",
    [((16, 20, 0), "found v16.20.0, need 18+"), (None, "Node.js 18+")],
    ids=["node-16", "node-absent"],
)
def test_node_below_18_or_absent_reports_missing(version, note_part, monkeypatch, isolated_db):
    from hireember import doctor

    monkeypatch.setattr(doctor, "get_node_version", lambda: version)

    check = doctor.check_node()
    assert check.name == "Node.js"
    assert check.status == "MISSING"
    assert note_part in check.note
    assert _status_of(_run_doctor(), "Node.js") == "MISSING"


def test_node_18_or_later_reports_ok(monkeypatch):
    from hireember import doctor

    monkeypatch.setattr(doctor, "get_node_version", lambda: (20, 11, 1))

    check = doctor.check_node()
    assert check.status == "OK"
    assert "v20.11.1" in check.note


def test_empty_path_reports_node_and_claude_missing(monkeypatch):
    from hireember import doctor

    monkeypatch.setenv("PATH", "")

    assert doctor.get_node_version() is None
    assert doctor.check_node().status == "MISSING"
    claude = doctor.check_claude()
    assert claude.name == "Claude Code CLI"
    assert claude.status == "MISSING"


def test_python_version_check():
    from hireember.doctor import check_python

    old = check_python((3, 10, 0))
    assert (old.name, old.status) == ("Python", "MISSING")
    assert "found 3.10.0, need 3.11+" in old.note

    new = check_python((3, 12, 4))
    assert (new.name, new.status, new.note) == ("Python", "OK", "3.12.4")


def test_database_check_missing_then_ok(tmp_path):
    from hireember.doctor import check_database

    missing_path = tmp_path / "absent.db"
    missing = check_database(missing_path)
    assert (missing.name, missing.status) == ("Database", "MISSING")
    assert "hireember init" in missing.note
    assert not missing_path.exists(), "check_database must not create the DB file"

    present_path = tmp_path / "present.db"
    init_db(present_path)
    present = check_database(present_path)
    assert (present.name, present.status) == ("Database", "OK")
    assert str(present_path) in present.note


def test_database_check_defaults_to_config_db_path(isolated_db):
    from hireember.doctor import check_database

    assert check_database().status == "MISSING"
    sqlite3.connect(isolated_db).execute("CREATE TABLE t (x INTEGER)").connection.commit()
    assert check_database().status == "OK"


def test_sources_check_lists_boards_without_linkedin():
    from hireember.doctor import check_sources

    check = check_sources({"sites": ["indeed", "linkedin", "zip_recruiter"]})
    assert check.name == "Job sources"
    assert check.status == "OK"
    assert "indeed" in check.note and "zip_recruiter" in check.note
    assert "linkedin" not in check.note.lower()

    default = check_sources({})
    assert default.status == "OK"
    assert "indeed" in default.note and "zip_recruiter" in default.note
    assert "linkedin" not in default.note.lower()
