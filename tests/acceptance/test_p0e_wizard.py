"""AC-5 (init writes models.toml), AC-18: init AI step and the Chromium offer."""

import pytest
from p0d_helpers import Script, console, output
from p0e_helpers import SECRET, isolate_models

Q_ENABLE = "Enable AI scoring and resume tailoring? [Y/n]"
Q_PROVIDER = "Provider (gemini/openai/custom)"
Q_MODEL = "Model"
Q_URL = "Base URL"
Q_KEY = "API key"
Q_DIFF = "Use a different model for tailoring and cover letters? [y/N]"
Q_CHROMIUM = "Playwright Chromium is not installed. Run 'playwright install chromium' now? [Y/n]"
LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    from hireember import config

    p = isolate_models(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
    return p


def _run(script):
    from hireember.wizard.init import run_ai_step

    c = console()
    run_ai_step(script, console=c)
    return output(c)


def test_declining_ai_writes_nothing(path):
    script = Script({Q_ENABLE: ["n"]})
    _run(script)
    assert script.log == [Q_ENABLE]
    assert not path.exists()


def test_fast_only_stores_one_tier_and_says_quality_follows(path, tmp_path):
    from hireember import models

    script = Script({Q_ENABLE: ["y"], Q_PROVIDER: ["gemini"], Q_MODEL: ["gemini-2.0-flash"],
                     Q_KEY: [SECRET], Q_DIFF: ["n"]})
    out = _run(script)
    data = models.load_models_file()
    assert set(data) == {"fast"}
    assert data["fast"]["provider"] == "gemini" and data["fast"]["model"] == "gemini-2.0-flash"
    assert data["fast"]["api_key"] == SECRET
    assert SECRET not in out
    assert "quality" in out.lower()
    s = models.resolve_tier("fast")
    assert (s.provider, s.api_key, s.source) == ("gemini", SECRET, "config file")
    env = tmp_path / ".env"
    assert not env.exists() or "GEMINI_API_KEY" not in env.read_text(encoding="utf-8")


def test_different_quality_model_is_stored_and_local_needs_no_key(path):
    from hireember import models

    script = Script({
        Q_ENABLE: ["y"],
        Q_PROVIDER: ["gemini", "custom"],
        Q_MODEL: ["gemini-2.0-flash", "llama3.1:70b"],
        Q_KEY: [SECRET],  # asked once: the local quality tier needs no key
        Q_URL: [LOCAL],
        Q_DIFF: ["y"],
    })
    _run(script)
    assert script.log.count(Q_KEY) == 1
    data = models.load_models_file()
    assert data["quality"]["provider"] == "custom"
    assert data["quality"]["model"] == "llama3.1:70b"
    assert data["quality"]["base_url"] == LOCAL
    assert not data["quality"].get("api_key")
    q = models.resolve_tier("quality")
    assert q.is_local and q.key_state == "not needed (local)"
    assert models.resolve_tier("fast").model == "gemini-2.0-flash"


def test_init_and_models_set_write_the_same_file(path):
    from hireember import models

    _run(Script({Q_ENABLE: ["y"], Q_PROVIDER: ["openai"], Q_MODEL: ["gpt-4o-mini"],
                 Q_KEY: [SECRET], Q_DIFF: ["n"]}))
    models.save_tier("quality", provider="custom", model="m", base_url=LOCAL)
    data = models.load_models_file()
    assert set(data) == {"fast", "quality"}
    assert data["fast"]["provider"] == "openai"


# -- Chromium offer -------------------------------------------------------

class Runner:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))

        class Done:
            pass

        d = Done()
        d.returncode = self.returncode
        return d


def _offer(monkeypatch, chromium, replies, runner):
    from hireember import doctor
    from hireember.wizard.init import offer_chromium_install

    monkeypatch.setattr(doctor, "chromium_path", lambda: chromium)
    script = Script(replies)
    c = console()
    result = offer_chromium_install(script, console=c, runner=runner)
    return result, script, output(c)


def test_no_prompt_when_chromium_installed(monkeypatch):
    runner = Runner()
    result, script, out = _offer(monkeypatch, "/pw/chromium", {}, runner)
    assert result is False and script.log == [] and runner.calls == []


def test_yes_runs_install_and_reports_installed(monkeypatch):
    runner = Runner(0)
    result, script, out = _offer(monkeypatch, None, {Q_CHROMIUM: ["y"]}, runner)
    assert runner.calls == [["playwright", "install", "chromium"]]
    assert result is True
    assert "Installed." in out


def test_failed_install_shows_manual_command_and_continues(monkeypatch):
    runner = Runner(1)
    result, script, out = _offer(monkeypatch, None, {Q_CHROMIUM: ["y"]}, runner)
    assert result is False
    assert "Run it yourself: playwright install chromium" in out
    assert "Installed." not in out


def test_declining_prints_command_and_does_not_run(monkeypatch):
    runner = Runner()
    result, script, out = _offer(monkeypatch, None, {Q_CHROMIUM: ["n"]}, runner)
    assert result is False and runner.calls == []
    assert "playwright install chromium" in out
