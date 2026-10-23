"""`hireember dashboard` command (implementation tests)."""

from typer.testing import CliRunner

from hireember.cli import app


def test_help_text():
    result = CliRunner().invoke(app, ["dashboard", "--help"])
    assert result.exit_code == 0
    assert "Open the local web dashboard." in result.output
    assert "--host" in result.output and "--port" in result.output and "--open" in result.output


def test_foreign_host_refused():
    result = CliRunner().invoke(app, ["dashboard", "--host", "0.0.0.0", "--port", "0"])
    assert result.exit_code == 2
    assert "Refusing to bind to 0.0.0.0." in " ".join(result.output.split())
