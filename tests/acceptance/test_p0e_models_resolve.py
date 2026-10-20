"""AC-2, AC-4, AC-5 (storage), AC-16: tier resolution and the models file."""

import os
import stat

import pytest
from p0e_helpers import GEMINI_URL, SECRET, isolate_models, write_models

LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    return isolate_models(monkeypatch, tmp_path)


def test_ac2_only_gemini_env_both_tiers_match_todays_client(path, monkeypatch):
    from hireember import llm, models

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    base_url, model, key = llm._detect_provider()
    for tier in ("fast", "quality"):
        s = models.resolve_tier(tier)
        assert (s.provider, s.model, s.base_url, s.api_key) == ("gemini", model, base_url, key)
        assert s.model == "gemini-2.0-flash" and s.base_url == GEMINI_URL
        assert s.source == "environment" and s.tier == tier
        assert s.key_state == "set"
    assert not path.exists()


def test_legacy_openai_and_local_env(path, monkeypatch):
    from hireember import models

    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    s = models.resolve_tier("quality")
    assert (s.provider, s.model, s.base_url) == ("openai", "gpt-4o-mini", "https://api.openai.com/v1")

    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("LLM_URL", LOCAL)
    monkeypatch.setenv("LLM_MODEL", "llama3.1")
    s = models.resolve_tier("fast")
    assert (s.provider, s.model, s.base_url) == ("custom", "llama3.1", LOCAL)
    assert s.is_local and s.key_state == "not needed (local)"


def test_ac4_local_base_url_without_key_resolves(path):
    from hireember import models

    write_models(path, f'[fast]\nprovider = "custom"\nmodel = "llama3.1"\nbase_url = "{LOCAL}"\n')
    s = models.resolve_tier("fast")
    assert (s.provider, s.model, s.base_url, s.api_key) == ("custom", "llama3.1", LOCAL, "")
    assert s.source == "config file"
    assert s.is_local and s.key_state == "not needed (local)"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_is_local_hosts(path, host):
    from hireember import models

    write_models(path, f'[fast]\nprovider = "custom"\nmodel = "m"\nbase_url = "http://{host}:8080/v1"\n')
    assert models.resolve_tier("fast").is_local is True


def test_remote_custom_url_is_not_local(path):
    from hireember import models

    write_models(path, '[fast]\nprovider = "custom"\nmodel = "m"\nbase_url = "https://llm.example.com/v1"\n')
    s = models.resolve_tier("fast")
    assert s.is_local is False and s.key_state == "not set"


def test_file_wins_over_env_and_other_tier_uses_env(path, monkeypatch):
    from hireember import models

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    write_models(path, f'[quality]\nprovider = "custom"\nmodel = "llama3.1:70b"\nbase_url = "{LOCAL}"\n')
    q = models.resolve_tier("quality")
    assert (q.model, q.source) == ("llama3.1:70b", "config file")
    f = models.resolve_tier("fast")
    assert (f.provider, f.model, f.source) == ("gemini", "gemini-2.0-flash", "environment")


def test_ac16_one_tier_in_file_other_unconfigured_without_env(path):
    from hireember import models

    write_models(path, f'[fast]\nprovider = "custom"\nmodel = "m"\nbase_url = "{LOCAL}"\n')
    with pytest.raises(models.TierNotConfigured) as e:
        models.resolve_tier("quality")
    assert str(e.value) == "quality tier is not configured. Run 'hireember models set quality' or 'hireember init'."
    assert isinstance(e.value, models.ModelsError)


def test_nothing_configured_raises_for_both(path):
    from hireember import models

    for tier in models.TIERS:
        with pytest.raises(models.TierNotConfigured):
            models.resolve_tier(tier)


def test_file_section_defaults_model_and_takes_key_from_env(path, monkeypatch):
    from hireember import models

    write_models(path, '[fast]\nprovider = "openai"\n')
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    s = models.resolve_tier("fast")
    assert (s.provider, s.model, s.api_key, s.source) == ("openai", "gpt-4o-mini", "oa-key", "config file")
    assert s.base_url == "https://api.openai.com/v1"


def test_non_local_tier_without_key_says_so(path):
    from hireember import models

    write_models(path, '[fast]\nprovider = "openai"\n')
    with pytest.raises(models.TierNotConfigured) as e:
        models.resolve_tier("fast")
    assert str(e.value) == (
        "fast tier has no API key. Set it with 'hireember models set fast --api-key ...' "
        "or the GEMINI_API_KEY / OPENAI_API_KEY variable."
    )


def test_bad_tier_name(path):
    from hireember import models

    with pytest.raises(ValueError, match="Tier must be 'fast' or 'quality'."):
        models.resolve_tier("medium")
    assert models.TIERS == ("fast", "quality")


def test_malformed_file_error_names_line_and_path(path):
    from hireember import models

    write_models(path, '[fast]\nmodel = "ok"\nbroken line here\n')
    with pytest.raises(models.ModelsConfigError) as e:
        models.resolve_tier("fast")
    msg = str(e.value)
    assert msg.startswith("models.toml is not valid TOML (line 3).")
    assert msg.endswith(f"Fix or delete it: {path}")
    assert "\n" not in msg
    with pytest.raises(models.ModelsConfigError):
        models.load_models_file()


def test_load_models_file_absent_and_present(path):
    from hireember import models

    assert models.load_models_file() == {}
    write_models(path, '[fast]\nmodel = "a"\n[quality]\nmodel = "b"\n')
    assert models.load_models_file() == {"fast": {"model": "a"}, "quality": {"model": "b"}}
    assert models.load_models_file(path) == models.load_models_file()


def test_save_tier_merges_and_keeps_other_tier(path):
    from hireember import models

    assert models.save_tier("fast", provider="custom", model="m1", base_url=LOCAL) == path
    models.save_tier("quality", provider="openai", model="gpt-x", api_key=SECRET)
    models.save_tier("fast", model="m2")
    data = models.load_models_file()
    assert data["fast"]["model"] == "m2"
    assert data["fast"]["provider"] == "custom" and data["fast"]["base_url"] == LOCAL
    assert data["quality"]["provider"] == "openai" and data["quality"]["api_key"] == SECRET
    assert models.resolve_tier("fast").model == "m2"


@pytest.mark.skipif(os.name != "posix", reason="owner-only mode applies on POSIX")
def test_save_tier_file_is_owner_only(path):
    from hireember import models

    models.save_tier("fast", provider="custom", model="m", base_url=LOCAL, api_key=SECRET)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_save_tier_rejects_bad_input_and_malformed_file(path, tmp_path):
    from hireember import models

    with pytest.raises(ValueError):
        models.save_tier("medium", model="x")
    with pytest.raises(ValueError):
        models.save_tier("fast", provider="mystery")
    assert not path.exists()

    bad = '[fast\nmodel = "x"\n'
    write_models(path, bad)
    with pytest.raises(models.ModelsConfigError):
        models.save_tier("fast", model="y")
    assert path.read_text(encoding="utf-8") == bad


def test_save_tier_explicit_path(path, tmp_path):
    from hireember import models

    other = tmp_path / "other.toml"
    assert models.save_tier("fast", model="x", provider="gemini", path=other) == other
    assert models.load_models_file(other)["fast"]["model"] == "x"
    assert not path.exists()


def test_get_client_requires_tier_and_uses_each_tiers_settings(path, monkeypatch):
    from hireember import llm

    write_models(
        path,
        f'[fast]\nprovider = "custom"\nmodel = "small"\nbase_url = "{LOCAL}"\n'
        '[quality]\nprovider = "custom"\nmodel = "big"\nbase_url = "http://localhost:9999/v1"\n',
    )
    with pytest.raises(TypeError):
        llm.get_client()
    fast, quality = llm.get_client("fast"), llm.get_client("quality")
    assert (fast.model, fast.base_url) == ("small", LOCAL)
    assert (quality.model, quality.base_url) == ("big", "http://localhost:9999/v1")
    assert fast is not quality
    assert llm.get_client("fast") is fast


def test_get_client_unconfigured_raises_runtime_error_with_message(path):
    from hireember import llm

    with pytest.raises(RuntimeError) as e:
        llm.get_client("quality")
    assert "quality tier is not configured" in str(e.value)


def test_get_client_legacy_env_gives_same_model_for_both(path, monkeypatch):
    from hireember import llm

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    a, b = llm.get_client("fast"), llm.get_client("quality")
    assert a.model == b.model == "gemini-2.0-flash"
    assert a.api_key == "gem-key"
