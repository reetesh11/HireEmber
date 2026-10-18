"""Shared helpers for the phase-3 apply acceptance tests (public surfaces only).

The "agent" in these tests is a plain Python function that reads a local fixture form
and drives a ``GateSession`` the way the real browser agent is told to.
"""

import json
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from p1_helpers import add_job  # noqa: F401  (re-exported)
from p2_helpers import widen_cli_console  # noqa: F401  (re-exported)

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_LINK = "http://127.0.0.1:9333"
COLOR_Q = "What is your favourite colour?"

PROFILE = {
    "personal": {"full_name": "Test Person", "email": "test@example.com", "phone": "555-0100"},
}


def write_profile(tmp_path, monkeypatch) -> dict:
    """Point the app at a temporary profile.json (no password key)."""
    import hireember.config as config

    path = tmp_path / "profile.json"
    path.write_text(json.dumps(PROFILE), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    return PROFILE


def add_ticket(conn, tmp_path, name, *, company="Acme", title=None, location=None, score=8) -> int:
    """Create a scored job and ticket with tailored resume files; return the ticket id."""
    from hireember.tickets import set_ticket_files

    url = f"https://jobs.example/{name}"
    tid = add_job(conn, url, title=title or f"Backend Engineer {name}",
                  location=location or f"City {name}", company=company, score=score)
    folder = tmp_path / name
    folder.mkdir(parents=True, exist_ok=True)
    txt = folder / "tailored_resume.txt"
    txt.write_text("Test Person\nBackend engineer", encoding="utf-8")
    (folder / "tailored_resume.pdf").write_bytes(b"%PDF-1.4\n%fixture\n")
    set_ticket_files(conn, tid, str(txt), "")
    conn.execute("UPDATE jobs SET tailored_resume_path = ? WHERE url = ?", (str(txt), url))
    conn.commit()
    return tid


def job_url(name: str) -> str:
    return f"https://jobs.example/{name}"


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.labels: dict[str, str] = {}
        self.fields: list[dict] = []
        self.text: list[str] = []
        self.body_attrs: dict[str, str] = {}
        self.captcha = False
        self._label_for = None
        self._skip = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "body":
            self.body_attrs = a
        elif tag == "label":
            self._label_for = a.get("for")
        elif tag in ("input", "textarea", "select"):
            kind = a.get("type", "text") if tag == "input" else tag
            self.fields.append({"id": a.get("id", ""), "type": kind.lower()})
        elif tag in ("script", "style", "title"):
            self._skip = True
        if "g-recaptcha" in a.get("class", "") or "h-captcha" in a.get("class", ""):
            self.captcha = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title"):
            self._skip = False
        if tag == "label":
            self._label_for = None

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text or self._skip:
            return
        if self._label_for is not None:
            self.labels[self._label_for] = text
        else:
            self.text.append(text)


def fetch(base_url: str, page: str) -> tuple[str, str]:
    url = base_url.rstrip("/") + "/forms/" + page
    with urllib.request.urlopen(url, timeout=5) as resp:
        return url, resp.read().decode("utf-8")


class FormRun:
    """What the fixture agent did on one form."""

    def __init__(self):
        self.filled: dict[str, str] = {}
        self.uploaded: str | None = None
        self.stopped_on: str | None = None
        self.submit_calls = 0
        self.injected: list[bool] = []
        self.resume_from = None


def drive(session, base_url: str, page: str, *, confirmation: str | None = "auto",
          run: FormRun | None = None) -> FormRun:
    """Act on a fixture page like the real agent: ask the session before every step."""
    run = run or FormRun()
    run.resume_from = session.resume_from
    url, html = fetch(base_url, page)
    parsed = _Page()
    parsed.feed(html)

    for line in parsed.text:
        run.injected.append(session.note_page_text(line))

    if parsed.body_attrs.get("data-page") == "signin":
        session.stop("account needed", url)
        run.stopped_on = "account needed"
        return run
    if parsed.body_attrs.get("data-role") == "closed":
        session.closed(" ".join(parsed.text[:1]))
        return run
    if parsed.captcha:
        session.stop("captcha", url)
        run.stopped_on = "captcha"
        return run

    for f in parsed.fields:
        label = parsed.labels.get(f["id"], f["id"])
        if f["type"] == "file":
            run.uploaded = Path(session.resume_path()).name
            continue
        decision = session.answer_field(label, f["type"])
        if decision.action == "stop":
            run.stopped_on = decision.reason
            return run
        run.filled[label] = decision.value

    if session.before_submit() == "stop":
        run.stopped_on = "review before submit"
        return run
    run.submit_calls += 1
    session.submit_pressed()
    link = f"{url}#confirmation" if confirmation == "auto" else confirmation
    session.submitted(link)
    return run


def agent_for(base_url: str, page: str, run: FormRun | None = None, **kw):
    """Return (agent, run): an agent callable for ``apply_ticket`` that drives ``page``."""
    run = run or FormRun()

    def agent(session):
        drive(session, base_url, page, run=run, **kw)

    return agent, run


def forbidden_agent(session):
    raise AssertionError("the agent must not be called")


def open_items(conn, ticket_id=None):
    from hireember.answers import list_queue

    items = list_queue(conn)
    return [i for i in items if ticket_id is None or i["ticket_id"] == ticket_id]



def make_env(tmp_path, monkeypatch):
    """(connection, tmp_path) on the default test database with a temporary profile."""
    from hireember.database import init_db

    write_profile(tmp_path, monkeypatch)
    return init_db(), tmp_path
