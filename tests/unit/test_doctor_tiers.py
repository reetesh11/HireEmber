import pytest

from hireember import config, doctor, models

LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    p = tmp_path / "models.toml"
    monkeypatch.setattr(config, "MODELS_PATH", p)
    return p


def _probe(ok, message=""):
    def probe(tier):
        s = models.resolve_tier(tier)
        return models.TierResult(tier, ok, s.provider, s.model, 0.0, message)
    return probe


def test_ok_warn_missing(path, monkeypatch):
    models.save_tier("fast", provider="custom", model="m", base_url=LOCAL)
    monkeypatch.setattr(models, "probe_tier", _probe(True))
    fast, quality = doctor.check_llm_tiers()
    assert (fast.status, fast.note) == ("OK", "custom / m, reachable")
    assert quality.status == "MISSING"
    monkeypatch.setattr(models, "probe_tier", _probe(False, "Cannot reach x"))
    assert doctor.check_llm_tiers()[0].note == "custom / m, not reachable: Cannot reach x"


def test_missing_key_is_reported_as_missing(path):
    models.save_tier("fast", provider="openai")
    fast = doctor.check_llm_tiers()[0]
    assert fast.status == "MISSING" and "no API key" in fast.note


def test_hints_never_mention_no_deps(path, monkeypatch):
    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    text = " ".join(c.note for c in doctor.run_checks())
    assert "--no-deps" not in text
    assert "playwright install chromium" in text
