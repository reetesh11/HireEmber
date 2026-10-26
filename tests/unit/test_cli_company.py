"""company add/remove/list CLI output."""

from typer.testing import CliRunner

from hireember.cli import app


def _run(*args):
    result = CliRunner().invoke(app, list(args))
    return result, " ".join(result.output.split())


def test_add_list_remove(isolated_db):
    r, out = _run("company", "add", "Acme", "--url", "https://acme.example", "--ats", "careers-page")
    assert r.exit_code == 0 and 'Added company "Acme".' in out
    r, out = _run("company", "list")
    assert "careers-page" in out and "Manual-only" in out
    r, out = _run("company", "remove", "Acme")
    assert r.exit_code == 0 and 'Removed company "Acme".' in out
    assert "No companies yet." in _run("company", "list")[1]
