import os
import stat

import pytest

from hireember import config, models

LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    p = tmp_path / "models.toml"
    monkeypatch.setattr(config, "MODELS_PATH", p)
    return p


def test_legacy_env_resolves_both_tiers_to_one_provider(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    fast, quality = models.resolve_tier("fast"), models.resolve_tier("quality")
    assert (fast.provider, fast.model) == (quality.provider, quality.model) == ("gemini", "gemini-2.0-flash")


def test_file_overrides_env_and_other_tier_falls_back(path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    models.save_tier("quality", provider="custom", model="big", base_url=LOCAL)
    assert models.resolve_tier("quality").model == "big"
    assert models.resolve_tier("fast").provider == "openai"


def test_malformed_file_leaves_bytes_unchanged(path):
    path.write_text("[fast\nx = 1\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(models.ModelsConfigError, match=r"^models.toml is not valid TOML \(line 1\)\."):
        models.save_tier("fast", model="m")
    assert path.read_bytes() == before


def test_save_tier_merges_fields_and_keeps_other_tier(path):
    models.save_tier("fast", provider="gemini", model="a", api_key='we"ird\\key')
    models.save_tier("quality", provider="custom", base_url=LOCAL)
    models.save_tier("fast", model="b")
    data = models.load_models_file()
    assert data["fast"] == {"provider": "gemini", "model": "b", "api_key": 'we"ird\\key'}
    assert data["quality"] == {"provider": "custom", "base_url": LOCAL}


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes")
def test_file_mode_is_owner_only(path):
    models.save_tier("fast", provider="gemini", api_key="k")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_key_origin(path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert models.key_origin(models.resolve_tier("fast")) == "set (environment)"
    models.save_tier("fast", provider="openai", api_key="x")
    assert models.key_origin(models.resolve_tier("fast")) == "set (config file)"
    models.save_tier("quality", provider="custom", base_url=LOCAL)
    assert models.key_origin(models.resolve_tier("quality")) == "not needed (local)"


def test_models_file_counts_as_llm_for_tier_gate(path):
    assert config.has_llm_configured() is False
    models.save_tier("fast", provider="custom", base_url=LOCAL)
    assert config.has_llm_configured() is True
