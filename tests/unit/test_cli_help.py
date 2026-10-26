"""--help exits 0 for every command on a fresh install (no profile, no database)."""

import pytest
from typer.testing import CliRunner

from hireember.cli import app

COMMANDS = ["init", "run", "apply", "status", "dashboard", "doctor", "schedule", "scheduler",
            "export", "answers", "queue", "company"]


@pytest.mark.parametrize("command", COMMANDS)
def test_help(isolated_db, command):
    r = CliRunner().invoke(app, [command, "--help"])
    assert r.exit_code == 0, r.output
    assert r.output.strip()
    assert not isolated_db.exists()


@pytest.mark.parametrize("sub", ["add", "remove", "list"])
def test_company_subcommand_help(isolated_db, sub):
    assert CliRunner().invoke(app, ["company", sub, "--help"]).exit_code == 0
