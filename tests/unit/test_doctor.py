"""Unit tests for hireember.doctor."""

import subprocess

from hireember import doctor
from hireember.database import close_connection, init_db

ORDER = [
    "Python", "profile.json", "resume.txt", "searches.yaml", "python-jobspy", "LLM API key",
    "Claude Code CLI", "Chrome/Chromium", "Node.js", "Database", "Job sources",
]


def test_check_python_threshold():
    assert doctor.check_python((3, 10, 0)).status == "MISSING"
    assert doctor.check_python((3, 11, 0)) == doctor.Check("Python", "OK", "3.11.0")


def _stub_node(monkeypatch, stdout):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None)
    monkeypatch.setattr(
        doctor.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=stdout, stderr=""),
    )


def test_get_node_version_parses(monkeypatch):
    _stub_node(monkeypatch, "v20.11.1\n")
    assert doctor.get_node_version() == (20, 11, 1)


def test_get_node_version_garbage(monkeypatch):
    _stub_node(monkeypatch, "not a version\n")
    assert doctor.get_node_version() is None


def test_check_database_missing_does_not_create(tmp_path):
    path = tmp_path / "nope.db"
    check = doctor.check_database(path)
    assert check.status == "MISSING"
    assert not path.exists()


def test_check_database_ok_after_init(tmp_path):
    path = tmp_path / "ok.db"
    init_db(path)
    close_connection(path)
    assert doctor.check_database(path).status == "OK"


def test_check_sources_never_lists_linkedin():
    check = doctor.check_sources({"sites": ["linkedin"]})
    assert "linkedin" not in check.note.lower()
    assert "JobSpy: none" in check.note
    assert check.status == "OK"  # Workday employers and career sites still count


def test_run_checks_order(isolated_db):
    assert [c.name for c in doctor.run_checks()] == ORDER
