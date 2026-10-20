"""AC-4, AC-5, AC-6, AC-15: the `hireember models` command and tier testing."""

import re

import httpx
import pytest
from p0e_helpers import SECRET, FakeClient, ProbeServer, free_port_url, isolate_models, write_models
from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli

LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    p = isolate_models(monkeypatch, tmp_path)
    monkeypatch.setenv("COLUMNS", "300")
    monkeypatch.setattr(cli, "console", Console(width=300))
    return p


def run(*args):
    return CliRunner().invoke(cli.app, ["models", *args])


def _line(output: str, word: str) -> str:
    for line in output.splitlines():
        if re.match(rf"^{word}\b", line):
            return line
    raise AssertionError(f"no line starting with {word!r} in:\n{output}")


# -- show -----------------------------------------------------------------

def test_show_prints_both_tiers_sources_and_no_key(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", SECRET)
    write_models(
        path,
        f'[quality]\nprovider = "custom"\nmodel = "llama3.1:70b"\nbase_url = "{LOCAL}"\napi_key = "{SECRET}-file"\n',
    )
    res = run("show")
    assert res.exit_code == 0, res.output
    out = res.output
    assert "Model tiers" in out
    assert out.index("fast") < out.index("quality")
    for label in ("provider:", "model:", "base url:", "key:", "source:"):
        assert out.count(label) == 2
    assert "gemini-2.0-flash" in out and "(preset)" in out
    assert "llama3.1:70b" in out and LOCAL in out
    assert "not needed (local)" in out
    assert "environment" in out and "config file" in out
    assert "SECRET" not in out and SECRET not in out


def test_show_key_set_from_file_is_reported_not_printed(path):
    write_models(path, f'[fast]\nprovider = "openai"\nmodel = "gpt-4o-mini"\napi_key = "{SECRET}"\n')
    out = run("show").output
    assert "set (config file)" in out
    assert SECRET not in out


def test_show_marks_unconfigured_tier(path):
    res = run("show")
    assert res.exit_code == 0, res.output
    assert res.output.count("not configured") >= 2
    assert "Traceback" not in res.output


def test_show_malformed_file_exits_1_with_one_line(path):
    write_models(path, "[fast\n")
    res = run("show")
    assert res.exit_code == 1
    assert "models.toml is not valid TOML (line 1)." in res.output
    assert "Traceback" not in res.output


# -- set ------------------------------------------------------------------

def test_set_saves_then_show_reflects_and_other_fields_stay(path):
    res = run("set", "fast", "--provider", "custom", "--model", "m1", "--base-url", LOCAL)
    assert res.exit_code == 0, res.output
    assert f"Saved fast tier to {path}." in res.output
    res = run("set", "fast", "--model", "m2")
    assert res.exit_code == 0, res.output
    out = run("show").output
    assert "m2" in out and "m1" not in out and LOCAL in out
    from hireember import models

    assert models.load_models_file()["fast"]["provider"] == "custom"


def test_set_api_key_is_stored_but_never_echoed(path):
    res = run("set", "quality", "--provider", "openai", "--model", "gpt-x", "--api-key", SECRET)
    assert res.exit_code == 0, res.output
    assert SECRET not in res.output
    assert SECRET in path.read_text(encoding="utf-8")
    assert SECRET not in run("show").output


def test_ac15_bad_tier_name(path):
    res = run("set", "medium", "--model", "x")
    assert res.exit_code != 0
    assert "Tier must be 'fast' or 'quality'." in res.output
    assert not path.exists()


def test_ac15_no_options(path):
    write_models(path, '[fast]\nmodel = "keep"\n')
    before = path.read_text(encoding="utf-8")
    res = run("set", "fast")
    assert res.exit_code != 0
    assert "Nothing to change. Pass --provider, --model, --base-url or --api-key." in res.output
    assert path.read_text(encoding="utf-8") == before


# -- test -----------------------------------------------------------------

def _fake_clients(monkeypatch, by_tier):
    import hireember.llm

    monkeypatch.setattr(hireember.llm, "get_client", lambda tier: by_tier[tier])


def test_test_command_reports_each_tier_and_exits_1_on_failure(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    write_models(path, f'[quality]\nprovider = "custom"\nmodel = "llama3.1:70b"\nbase_url = "{LOCAL}"\n')
    _fake_clients(monkeypatch, {
        "fast": FakeClient("hi"),
        "quality": FakeClient(error=httpx.ConnectError("connection refused")),
    })
    res = run("test")
    assert res.exit_code == 1, res.output
    out = res.output
    assert re.search(r"^fast\s+ok\s+gemini-2\.0-flash \(\d+(\.\d+)?s\)", out, re.M), out
    q = _line(out, "quality")
    assert re.match(r"^quality\s+FAILED\s+Cannot reach http://localhost:11434/v1", q), q
    assert out.index("fast") < out.index("quality")
    assert "Traceback" not in out and "ConnectError" not in out


def test_test_command_all_ok_exits_0_and_prints_both_for_shared_model(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    fast, quality = FakeClient("hi"), FakeClient("hi")
    _fake_clients(monkeypatch, {"fast": fast, "quality": quality})
    res = run("test")
    assert res.exit_code == 0, res.output
    assert re.search(r"^fast\s+ok\s+gemini-2\.0-flash", res.output, re.M)
    assert re.search(r"^quality\s+ok\s+gemini-2\.0-flash", res.output, re.M)
    assert fast.calls == 1 and quality.calls == 1


def test_ac4_local_tier_without_key_is_tested(path, monkeypatch):
    write_models(
        path,
        f'[fast]\nprovider = "custom"\nmodel = "a"\nbase_url = "{LOCAL}"\n'
        f'[quality]\nprovider = "custom"\nmodel = "b"\nbase_url = "{LOCAL}"\n',
    )
    _fake_clients(monkeypatch, {"fast": FakeClient("hi"), "quality": FakeClient("hi")})
    res = run("test")
    assert res.exit_code == 0, res.output
    assert re.search(r"^fast\s+ok\s+a ", res.output, re.M)
    assert re.search(r"^quality\s+ok\s+b ", res.output, re.M)


def test_ac6_unconfigured_tiers_give_one_line_each_no_traceback(path):
    res = run("test")
    assert res.exit_code == 1
    for tier in ("fast", "quality"):
        line = _line(res.output, tier)
        assert re.match(rf"^{tier}\s+FAILED\s+.*not configured", line), line
    assert "Traceback" not in res.output


def test_ac6_malformed_file_is_reported_without_traceback(path):
    write_models(path, "[fast\n")
    res = run("test")
    assert res.exit_code == 1
    assert "models.toml is not valid TOML (line 1)." in res.output
    assert "Traceback" not in res.output


# -- test_tier / probe_tier / friendly_error --------------------------------

def _settings(path, base_url, provider="custom", model="m"):
    from hireember import models

    write_models(path, f'[fast]\nprovider = "{provider}"\nmodel = "{model}"\nbase_url = "{base_url}"\napi_key = "k"\n')
    return models.resolve_tier("fast")


def _status_error(code):
    req = httpx.Request("POST", "http://x/v1/chat/completions")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(code, request=req))


@pytest.mark.parametrize(
    "error, expected",
    [
        (httpx.ConnectError("refused"), "Cannot reach http://127.0.0.1:1/v1"),
        (_status_error(401), "Key rejected by custom"),
        (_status_error(403), "Key rejected by custom"),
        (_status_error(404), "Model 'm' not found"),
        (httpx.ReadTimeout("slow"), "Request timed out"),
    ],
)
def test_friendly_error_mapping(path, error, expected):
    from hireember import models

    settings = _settings(path, "http://127.0.0.1:1/v1")
    msg = models.friendly_error(error, settings)
    assert msg == expected


def test_tier_test_never_raises_and_is_one_line(path, monkeypatch):
    import hireember.llm
    from hireember import models

    _settings(path, "http://127.0.0.1:1/v1", model="m")
    monkeypatch.setattr(hireember.llm, "get_client",
                        lambda tier: FakeClient(error=_status_error(401)))
    r = models.test_tier("fast")
    assert (r.tier, r.ok, r.model) == ("fast", False, "m")
    assert r.message == "Key rejected by custom"
    assert "Traceback" not in r.message and "HTTPStatusError" not in r.message

    monkeypatch.setattr(hireember.llm, "get_client", lambda tier: FakeClient("hello"))
    r = models.test_tier("fast")
    assert r.ok is True and r.seconds >= 0 and r.provider == "custom"


def test_tier_test_unconfigured_returns_message(path):
    from hireember import models

    r = models.test_tier("quality")
    assert r.ok is False
    assert r.message == "quality tier is not configured. Run 'hireember models set quality' or 'hireember init'."


def test_probe_tier_hits_models_endpoint_only(path):
    from hireember import models

    srv = ProbeServer(200)
    try:
        _settings(path, srv.url)
        r = models.probe_tier("fast")
        assert r.ok is True
        assert srv.paths == ["/v1/models"]
    finally:
        srv.close()


def test_probe_tier_rejected_key_and_server_error(path):
    from hireember import models

    srv = ProbeServer(401)
    try:
        _settings(path, srv.url)
        r = models.probe_tier("fast")
        assert (r.ok, r.message) == (False, "Key rejected by custom")
        srv.status = 500
        assert models.probe_tier("fast").ok is False
        srv.status = 404
        assert models.probe_tier("fast").ok is True  # any response below 500 counts as reachable
    finally:
        srv.close()


def test_probe_tier_unreachable_url(path):
    from hireember import models

    url = free_port_url()
    _settings(path, url)
    r = models.probe_tier("fast")
    assert r.ok is False and r.message == f"Cannot reach {url}"


def test_probe_tier_unconfigured_never_raises(path):
    from hireember import models

    r = models.probe_tier("fast")
    assert r.ok is False and "not configured" in r.message
