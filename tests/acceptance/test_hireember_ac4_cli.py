"""Rename AC-4: the `hireember` CLI exposes the same commands and reports its version."""

import os
import subprocess
import sys
from pathlib import Path

import typer
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS = {"init", "run", "apply", "status", "dashboard", "doctor", "answers", "queue", "resume",
            "company", "ticket"}


def test_help_exits_0_and_lists_exactly_the_six_commands():
    from hireember.cli import app

    assert isinstance(app, typer.Typer)
    assert app.info.name == "hireember"
    assert set(typer.main.get_command(app).commands) == COMMANDS

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for name in COMMANDS:
        assert name in result.output, f"{name!r} missing from --help:\n{result.output}"


def test_help_says_hireember_and_not_applypilot():
    from hireember.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "HireEmber" in result.output
    assert "applypilot" not in result.output.lower()


def test_version_flags_print_hireember_version():
    from hireember.cli import app

    for flag in ("--version", "-V"):
        result = CliRunner().invoke(app, [flag])
        assert result.exit_code == 0, result.output
        assert result.output.strip() == "hireember 0.3.0"


def test_python_dash_m_hireember_runs_the_cli(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["HIREEMBER_DIR"] = str(tmp_path / "data")
    proc = subprocess.run(
        [sys.executable, "-m", "hireember", "--version"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "hireember 0.3.0"
