import pytest
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from hireember import config

SECRET = "sk-unit-secret"


@pytest.fixture
def path(monkeypatch, tmp_path):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    p = tmp_path / "models.toml"
    monkeypatch.setattr(config, "MODELS_PATH", p)
    monkeypatch.setattr(cli, "console", Console(width=300))
    return p


def run(*args):
    return CliRunner().invoke(cli.app, ["models", *args])


def test_show_never_prints_env_or_file_keys(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    run("set", "quality", "--provider", "openai", "--api-key", SECRET + "-file")
    out = run("show").output
    assert SECRET not in out
    assert "set (environment)" in out and "set (config file)" in out


def test_set_round_trip_and_messages(path):
    assert run("set", "fast", "--provider", "custom", "--base-url", "http://localhost:1/v1", "--model", "m").exit_code == 0
    assert "Saved fast tier" in run("set", "fast", "--model", "n").output
    assert "n" in run("show").output
    bad = run("set", "slow", "--model", "x")
    assert bad.exit_code == 1 and "Tier must be 'fast' or 'quality'." in bad.output
    none = run("set", "fast")
    assert none.exit_code == 1 and none.output.startswith("Nothing to change.")
    bad = run("set", "fast", "--provider", "mystery")
    assert bad.exit_code == 1 and "Traceback" not in bad.output


def test_test_against_unreachable_url_is_one_line(path):
    run("set", "fast", "--provider", "custom", "--model", "m", "--base-url", "http://127.0.0.1:1/v1")
    run("set", "quality", "--provider", "custom", "--model", "m", "--base-url", "http://127.0.0.1:1/v1")
    res = run("test")
    assert res.exit_code == 1
    assert len(res.output.strip().splitlines()) == 2
    assert "Cannot reach http://127.0.0.1:1/v1" in res.output
    assert "Traceback" not in res.output
