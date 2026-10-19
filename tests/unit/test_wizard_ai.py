from scripted import Script, console, output

from hireember import config, models
from hireember.wizard.init import run_ai_step

Q_ENABLE = "Enable AI scoring and resume tailoring? [Y/n]"


def _setup(monkeypatch, tmp_path):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "MODELS_PATH", tmp_path / "models.toml")


def test_default_answers_enable_and_use_preset_defaults(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    script = Script({Q_ENABLE: [""], "Provider (gemini/openai/custom)": [""], "Model": [""], "API key": ["k"],
                     "Use a different model for tailoring and cover letters? [y/N]": [""]})
    c = console()
    run_ai_step(script, console=c)
    assert models.load_models_file() == {"fast": {"provider": "gemini", "model": "gemini-2.0-flash",
                                                  "api_key": "k"}}
    assert "API key" not in output(c) or "= k" not in output(c)


def test_invalid_provider_is_asked_again(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    script = Script({Q_ENABLE: ["y"], "Provider (gemini/openai/custom)": ["bogus", "openai"], "Model": ["gpt-x"],
                     "API key": ["k"], "Use a different model for tailoring and cover letters? [y/N]": ["n"]})
    run_ai_step(script, console=console())
    assert models.load_models_file()["fast"]["provider"] == "openai"
