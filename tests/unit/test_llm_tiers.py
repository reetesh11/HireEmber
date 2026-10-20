import pytest

from hireember import config, llm, models


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "MODELS_PATH", tmp_path / "models.toml")
    monkeypatch.setattr(llm, "_clients", {})


def test_no_default_tier():
    with pytest.raises(TypeError):
        llm.get_client()


def test_distinct_settings_give_distinct_clients_and_shared_settings_share():
    models.save_tier("fast", provider="custom", model="a", base_url="http://localhost:1/v1")
    models.save_tier("quality", provider="custom", model="b", base_url="http://localhost:1/v1")
    assert llm.get_client("fast") is not llm.get_client("quality")
    models.save_tier("quality", model="a")
    assert llm.get_client("fast") is llm.get_client("quality")
