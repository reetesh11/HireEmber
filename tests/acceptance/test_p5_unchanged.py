"""Phase 5 unchanged behaviour: --help on the existing commands on a fresh install (AC-7)."""

import pytest
from typer.testing import CliRunner


@pytest.mark.parametrize("cmd", ["init", "run", "apply", "status", "dashboard", "doctor", "answers", "queue", "company"])
def test_existing_command_help_exits_zero(isolated_db, cmd):
    from hireember.cli import app

    r = CliRunner().invoke(app, [cmd, "--help"])
    assert r.exit_code == 0, r.output
    assert r.output.strip()
    assert not isolated_db.exists()
