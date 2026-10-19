"""AC-6, AC-10 (doctor side), AC-11: doctor tier lines, jobspy and Playwright Chromium checks."""

import sys

import pytest
from p0e_helpers import isolate_models, write_models
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli

LOCAL = "http://localhost:11434/v1"
ORDER = [
    "Python", "profile.json", "resume.txt", "searches.yaml", "python-jobspy", "Playwright Chromium",
    "LLM fast", "LLM quality", "Claude Code CLI", "Chrome/Chromium", "Node.js", "Database", "Job sources",
]
MISSING_NOTE = "not configured — run 'hireember models set {t}' or 'hireember init'"


@pytest.fixture
def path(monkeypatch, tmp_path, isolated_db):
    p = isolate_models(monkeypatch, tmp_path)
    monkeypatch.setenv("COLUMNS", "300")
    monkeypatch.setattr(cli, "console", Console(width=300))
    return p


def _fake_probe(monkeypatch, ok_by_tier, message="Cannot reach http://localhost:11434/v1"):
    from hireember import models

    def probe(tier):
        s = models.resolve_tier(tier)
        ok = ok_by_tier[tier]
        return models.TierResult(tier, ok, s.provider, s.model, 0.0, "" if ok else message)

    monkeypatch.setattr(models, "probe_tier", probe)


def _checks():
    from hireember import doctor

    return {c.name: c for c in doctor.check_llm_tiers()}


def test_run_checks_order(path, monkeypatch):
    from hireember import doctor

    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    assert [c.name for c in doctor.run_checks()] == ORDER


def test_unconfigured_tiers_are_missing_with_hint(path):
    checks = _checks()
    assert list(checks) == ["LLM fast", "LLM quality"]
    for tier in ("fast", "quality"):
        c = checks[f"LLM {tier}"]
        assert (c.status, c.note) == ("MISSING", MISSING_NOTE.format(t=tier))


def test_reachable_tier_is_ok_and_unreachable_is_warn(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    write_models(path, f'[quality]\nprovider = "custom"\nmodel = "llama3.1:70b"\nbase_url = "{LOCAL}"\n')
    _fake_probe(monkeypatch, {"fast": True, "quality": False})
    checks = _checks()
    assert (checks["LLM fast"].status, checks["LLM fast"].note) == ("OK", "gemini / gemini-2.0-flash, reachable")
    q = checks["LLM quality"]
    assert q.status == "WARN"
    assert q.note == "custom / llama3.1:70b, not reachable: Cannot reach http://localhost:11434/v1"


def test_malformed_models_file_is_missing_with_error_text(path):
    write_models(path, "[fast\n")
    for c in _checks().values():
        assert c.status == "MISSING"
        assert c.note.startswith("models.toml is not valid TOML (line 1).")


def test_doctor_cli_shows_tier_lines_without_traceback_or_no_deps(path, monkeypatch):
    from hireember import doctor

    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    res = CliRunner().invoke(cli.app, ["doctor"])
    out = res.output
    assert res.exit_code == 0, out
    assert "LLM fast" in out and "LLM quality" in out
    assert MISSING_NOTE.format(t="fast") in out and MISSING_NOTE.format(t="quality") in out
    assert "LLM API key" not in out
    assert "--no-deps" not in out
    assert "Traceback" not in out


def test_doctor_cli_with_malformed_file_has_no_traceback(path, monkeypatch):
    write_models(path, "[fast\n")
    res = CliRunner().invoke(cli.app, ["doctor"])
    assert res.exit_code == 0, res.output
    assert "models.toml is not valid TOML (line 1)." in res.output
    assert "Traceback" not in res.output


def test_jobspy_check_import_failure_names_interpreter(monkeypatch):
    from hireember import doctor

    monkeypatch.setitem(sys.modules, "jobspy", None)  # makes `import jobspy` raise ImportError
    c = doctor._check_jobspy()
    assert (c.name, c.status) == ("python-jobspy", "WARN")
    assert c.note == f"Not importable. Reinstall hireember in the active Python: {sys.executable} -m pip install -e ."
    assert "--no-deps" not in c.note


def test_chromium_ok_and_missing(monkeypatch):
    from hireember import doctor

    monkeypatch.setattr(doctor, "chromium_path", lambda: "/pw/chromium-1/chrome")
    assert doctor.check_playwright_chromium() == doctor.Check("Playwright Chromium", "OK", "/pw/chromium-1/chrome")
    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    assert doctor.check_playwright_chromium() == doctor.Check(
        "Playwright Chromium", "MISSING", "Run: playwright install chromium")


def test_doctor_cli_mentions_playwright_install_when_chromium_missing(path, monkeypatch):
    from hireember import doctor

    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    out = CliRunner().invoke(cli.app, ["doctor"]).output
    assert "playwright install chromium" in out
    monkeypatch.setattr(doctor, "chromium_path", lambda: "/pw/chromium-1/chrome")
    out = CliRunner().invoke(cli.app, ["doctor"]).output
    assert "/pw/chromium-1/chrome" in out
