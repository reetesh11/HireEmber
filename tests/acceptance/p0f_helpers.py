"""Shared helpers for the phase-0f acceptance tests (public surfaces only)."""

import io
import json
import stat
import sys

from rich.console import Console

SECRET = "sk-SECRET-VALUE-98765"
LOCAL = "http://localhost:11434/v1"

Q_FAST = "Set up the fast model now? [Y/n]"
Q_QUALITY = "Set up the quality model now? [Y/n]"
Q_SAME = "Use the same settings as the fast tier? [Y/n]"
Q_RESUME = "Add your resume now? [Y/n]"
Q_PROFILE = "Run the profile step of init now? [Y/n]"
Q_SEARCH = "Run the search step of init now? [Y/n]"
Q_BROWSER = "Install the Playwright browser now (playwright install chromium)? [Y/n]"
Q_PROVIDER = "Provider (gemini/openai/custom)"
Q_MODEL = "Model"
Q_URL = "Base URL"
Q_KEY = "API key"
Q_PATH = "Resume file path"
Q_LOOKS_RIGHT = "Does this look right? [Y/n]"

ALL_STAGES = ["discover", "enrich", "score", "tailor", "cover", "pdf"]


def wide_console() -> Console:
    return Console(file=io.StringIO(), width=300)


def out_of(c: Console) -> str:
    return " ".join(c.file.getvalue().split())


def flat(text: str) -> str:
    return " ".join(text.split())


class Ask:
    """A scripted ``ask_user``: replies per exact question (consumed in order), records every call.

    An unscripted question fails the test. A reply that is an exception class or instance is raised.
    """

    def __init__(self, replies=None):
        self.replies = {k: list(v) for k, v in (replies or {}).items()}
        self.log: list[str] = []
        self.kwargs: list[dict] = []

    def __call__(self, question, **kwargs):
        self.log.append(question)
        self.kwargs.append(kwargs)
        queue = self.replies.get(question)
        if not queue:
            raise AssertionError(f"unscripted question: {question!r} (asked so far: {self.log})")
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, BaseException) or (isinstance(reply, type) and issubclass(reply, BaseException)):
            raise reply
        return reply


class NeverAsk(Ask):
    """Fails the test the moment anything is asked."""


class World:
    """An isolated HireEmber data folder whose settings can be switched on one at a time."""

    def __init__(self, monkeypatch, tmp_path, isolated_db):
        from p0e_helpers import isolate_models

        from hireember import config, database, doctor, models

        self.mp = monkeypatch
        self.tmp = tmp_path
        self.models_path = isolate_models(monkeypatch, tmp_path)
        self.data = tmp_path / "data"
        self.data.mkdir()
        self.cfgdir = tmp_path / "cfg"
        self.cfgdir.mkdir()
        (self.cfgdir / "sites.yaml").write_text("sites: []\n", encoding="utf-8")
        (self.cfgdir / "employers.yaml").write_text("employers: {}\n", encoding="utf-8")
        for name, value in {
            "APP_DIR": self.data,
            "CONFIG_DIR": self.cfgdir,
            "RESUME_PATH": self.data / "resume.txt",
            "RESUME_PDF_PATH": self.data / "resume.pdf",
            "PROFILE_PATH": self.data / "profile.json",
            "SEARCH_CONFIG_PATH": self.data / "searches.yaml",
            "ENV_PATH": self.data / ".env",
        }.items():
            monkeypatch.setattr(config, name, value)
        self.config = config
        self.models = models
        self.conn = database.init_db()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        monkeypatch.setenv("PATH", str(self.bin))
        self.browser_installed = True
        self.chrome_installed = True
        monkeypatch.setattr(doctor, "chromium_path", lambda: "/fake/chromium" if self.browser_installed else None)

        def chrome():
            if self.chrome_installed:
                return "/fake/chrome"
            raise FileNotFoundError("no chrome")

        monkeypatch.setattr(config, "get_chrome_path", chrome)
        self.probed: list[str] = []
        self.probe_ok = True

        def probe(tier):
            self.probed.append(tier)
            return models.TierResult(tier, self.probe_ok, "custom", "m", 0.0, "" if self.probe_ok else "boom")

        monkeypatch.setattr(models, "probe_tier", probe)

    # -- switches --------------------------------------------------------
    def tier(self, name, *, provider="custom", model="m1", base_url=LOCAL, api_key=None):
        self.models.save_tier(name, provider=provider, model=model, base_url=base_url, api_key=api_key)

    def resume(self, *, text=True, registered=True):
        src = self.tmp / "src_resume.txt"
        src.write_text("Jane Doe\nSenior engineer with many years of experience.\n", encoding="utf-8")
        if text:
            (self.data / "resume.txt").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        if registered:
            from hireember import resumes

            resumes.add_resume(self.conn, src, "Registered one")

    def profile(self):
        (self.data / "profile.json").write_text(json.dumps({"personal": {"country": "Canada"}}), encoding="utf-8")

    def search(self, sites=()):
        import yaml

        (self.data / "searches.yaml").write_text(yaml.safe_dump({"sites": list(sites), "queries": []}),
                                                 encoding="utf-8")

    def claude(self):
        exe = self.bin / "claude"
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    def tailored(self):
        from hireember.database import store_jobs

        store_jobs(self.conn, [{"url": "https://j/1", "title": "Dev", "company": "Acme", "location": "Toronto"}],
                   "S", "t")
        self.conn.execute("UPDATE jobs SET tailored_resume_path = '/x/t.txt' WHERE url = 'https://j/1'")
        self.conn.commit()

    def block_jobspy(self):
        self.mp.setitem(sys.modules, "jobspy", None)

    def everything(self):
        self.tier("fast")
        self.tier("quality")
        self.resume()
        self.profile()
        self.search()
        self.claude()
        self.tailored()
