"""Rename AC-10: user-facing text says HireEmber / `hireember` / ~/.hireember."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD = "apply" + "pilot"
# Same lines as: grep -rn "<old> init\|<old> run\|<old> apply\|<old> doctor\|~/.<old>" src README.md ...
PATTERN = re.compile(OLD + r" init|" + OLD + r" run|" + OLD + r" apply|" + OLD + r" doctor|~/." + OLD)
LEGACY_FALLBACK_FILE = Path("src") / "hireember" / "config.py"


def _files():
    for path in sorted((REPO_ROOT / "src").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            yield path
    for name in ("README.md", "CONTRIBUTING.md", ".env.example"):
        yield REPO_ROOT / name


def test_no_old_commands_or_data_folder_outside_legacy_fallback():
    hits = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(REPO_ROOT)
        if rel == LEGACY_FALLBACK_FILE:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert hits == [], "old command or folder names remain:\n" + "\n".join(hits)


def test_env_example_header():
    lines = (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# HireEmber Environment Configuration"
    assert lines[1] == "# Copy to ~/.hireember/.env and fill in your values."


@pytest.mark.parametrize("name", ["searches.example.yaml", "employers.yaml", "sites.yaml"])
def test_package_yaml_headers_say_hireember(name):
    text = (REPO_ROOT / "src" / "hireember" / "config" / name).read_text(encoding="utf-8")
    header_lines = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        header_lines.append(line)
    header = "\n".join(header_lines)
    assert "HireEmber" in header, header
    assert "ApplyPilot" not in header and OLD not in header, header
    if name == "searches.example.yaml":
        assert "~/.hireember/searches.yaml" in header, header
        assert "hireember init" in header, header


def test_doctor_header_and_missing_notes_say_hireember(isolated_db):
    from hireember.cli import app
    from hireember.doctor import run_checks

    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "HireEmber Doctor" in result.output
    assert "ApplyPilot" not in result.output

    notes = {c.name: (c.status, c.note) for c in run_checks()}
    for name in ("profile.json", "resume.txt", "searches.yaml", "Database"):
        status, note = notes[name]
        assert status in ("MISSING", "WARN"), (name, status, note)
        assert "hireember init" in note, (name, note)
        assert OLD not in note, (name, note)
    assert "run 'hireember init' or 'hireember run'" in notes["Database"][1]


def test_status_header_says_hireember(isolated_db):
    from hireember.cli import app

    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "HireEmber Pipeline Status" in result.output
    assert "ApplyPilot" not in result.output


def test_dashboard_html_title_says_hireember(isolated_db, tmp_path):
    from hireember.database import init_db
    from hireember.view import generate_dashboard

    init_db()
    out = Path(generate_dashboard(str(tmp_path / "dashboard.html")))
    html = out.read_text(encoding="utf-8")
    assert "<title>HireEmber Dashboard</title>" in html
    assert "<h1>HireEmber Dashboard</h1>" in html
    assert "ApplyPilot" not in html


def test_missing_profile_error_says_hireember_init(monkeypatch, tmp_path):
    import hireember.config

    monkeypatch.setattr(hireember.config, "PROFILE_PATH", tmp_path / "profile.json")
    with pytest.raises(FileNotFoundError) as excinfo:
        hireember.config.load_profile()
    assert "hireember init" in str(excinfo.value)
