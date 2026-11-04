from typer.testing import CliRunner

import hireember.cli as cli


def run(*args):
    return CliRunner().invoke(cli.app, ["add-job", *args])


def test_text_file_missing_is_exit_1(tmp_path):
    result = run("https://a.example/1", "--text", str(tmp_path / "nope.txt"))
    assert result.exit_code == 1 and "could not be read" in result.output


def test_options_are_checked_before_anything_runs(tmp_path):
    assert run("https://a.example/1", "--no-review").exit_code == 2
    assert run("https://a.example/1", "https://a.example/2", "--text", str(tmp_path)).exit_code == 2


def test_help_mentions_urls():
    out = CliRunner().invoke(cli.app, ["--help"]).output
    assert "add-job" in out and "URL" in out
