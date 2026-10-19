from p0d_helpers import Script, console, output

from hireember import doctor
from hireember.wizard.init import offer_chromium_install

Q = "Playwright Chromium is not installed. Run 'playwright install chromium' now? [Y/n]"


class Done:
    def __init__(self, code):
        self.returncode = code


def test_default_answer_runs_the_installer(monkeypatch):
    monkeypatch.setattr(doctor, "chromium_path", lambda: None)
    calls = []
    c = console()
    ok = offer_chromium_install(Script({Q: [""]}), console=c, runner=lambda cmd: calls.append(cmd) or Done(0))
    assert ok and calls == [["playwright", "install", "chromium"]]


def test_missing_installer_binary_does_not_abort(monkeypatch):
    monkeypatch.setattr(doctor, "chromium_path", lambda: None)

    def runner(cmd):
        raise FileNotFoundError("playwright")

    c = console()
    assert offer_chromium_install(Script({Q: ["y"]}), console=c, runner=runner) is False
    assert "Run it yourself: playwright install chromium" in output(c)


def test_no_prompt_when_installed(monkeypatch):
    monkeypatch.setattr(doctor, "chromium_path", lambda: "/pw/chrome")
    script = Script({})
    assert offer_chromium_install(script, console=console()) is False
    assert script.log == []
