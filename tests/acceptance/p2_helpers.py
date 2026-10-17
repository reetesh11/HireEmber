"""Shared helpers for the phase-2 acceptance tests (public surfaces only)."""

import copy
import json
import uuid
from pathlib import Path

from p1_helpers import add_job  # noqa: F401  (re-exported)

REPO_ROOT = Path(__file__).resolve().parents[2]

PROFILE = {
    "personal": {"full_name": "Test Person", "email": "test@example.com", "phone": "555-0100"},
    "experience": {"years_of_experience_total": "3", "target_role": "backend engineer"},
    "skills_boundary": {
        "languages": ["Python", "SQL", "JavaScript"],
        "frameworks": ["FastAPI", "Flask", "React"],
        "tools": ["Git", "Linux"],
    },
    "resume_facts": {
        "preserved_companies": ["Company A", "Company B"],
        "preserved_projects": ["Project X", "Project Y"],
        "preserved_school": "Your University",
        "real_metrics": ["50% improvement", "10x faster"],
    },
}

VALID_TAILOR = {
    "title": "Backend Engineer",
    "summary": "Built backend services in Python for small teams.",
    "skills": {"Languages": "Python, SQL", "Frameworks": "FastAPI", "Tools": "Git"},
    "experience": [
        {"header": "Company A", "subtitle": "Python | 2020-2022", "bullets": ["Built APIs with FastAPI."]},
        {"header": "Company B", "subtitle": "SQL | 2018-2020", "bullets": ["Wrote reporting queries."]},
    ],
    "projects": [{"header": "Project X", "subtitle": "Python", "bullets": ["Wrote a log parser."]}],
    "education": "Your University | Bachelor's Degree",
}

LETTER = "Dear Hiring Manager,\n\nI build backend services in Python and would like to help your team.\n\nTest Person"


def profile() -> dict:
    return copy.deepcopy(PROFILE)


def tailor_json(**changes) -> dict:
    data = copy.deepcopy(VALID_TAILOR)
    data.update(changes)
    return data


def bad_employer_tailor() -> dict:
    data = tailor_json()
    data["experience"].append(
        {"header": "Acme Corp", "subtitle": "Python | 2022", "bullets": ["Built internal tools."]}
    )
    return data


def bad_skill_tailor() -> dict:
    return tailor_json(skills={"Languages": "Python, SQL", "Tools": "Git, Kubernetes"})


class FakeLLM:
    def __init__(self):
        self.calls = {"scorer": [], "tailor": [], "cover_letter": []}

    def texts(self, name: str) -> str:
        return "\n".join(m["content"] for msgs in self.calls[name] for m in msgs)


def install_fake_llm(monkeypatch, *, score=8, reasoning="Fits well.", tailor=None, letter=LETTER,
                     score_error=None) -> FakeLLM:
    fake = FakeLLM()
    tailor_payload = json.dumps(tailor if tailor is not None else VALID_TAILOR)

    def responder(name):
        if name == "scorer":
            def r(messages):
                if score_error:
                    raise RuntimeError(score_error)
                return f"SCORE: {score}\nKEYWORDS: a, b\nREASONING: {reasoning}"
        elif name == "tailor":
            def r(messages):
                return tailor_payload
        else:
            def r(messages):
                return letter
        return r

    def make(name):
        respond = responder(name)

        class Client:
            def chat(self, messages, max_tokens=None, temperature=None):
                fake.calls[name].append(messages)
                return respond(messages)

        return lambda *a, **k: Client()

    for name in ("scorer", "tailor", "cover_letter"):
        monkeypatch.setattr(f"hireember.scoring.{name}.get_client", make(name))
    return fake


def store_job(conn, url, title="Backend Engineer", description="Build APIs in Python."):
    """Store one job (unique title suffix keeps output file names distinct) and return its url."""
    from hireember.database import store_jobs

    full_title = f"{title} {uuid.uuid4().hex[:6]}"
    store_jobs(conn, [{"url": url, "title": full_title, "location": "Berlin", "company": "Acme"}],
               "TestSite", "test")
    conn.execute("UPDATE jobs SET full_description=? WHERE url=?", (description, url))
    conn.commit()
    return url


def make_resume(conn, tmp_path, name, tags, text):
    from hireember.resumes import add_resume

    path = tmp_path / f"{name.replace(' ', '_')}.txt"
    path.write_text(text, encoding="utf-8")
    return add_resume(conn, path, name, tags)


def ticket_row(conn, ticket_id):
    from hireember.tickets import get_ticket

    return get_ticket(conn, ticket_id)


def widen_cli_console(monkeypatch):
    """Give the CLI a wide console so table cells are not wrapped in captured output."""
    import hireember.cli as cli
    from rich.console import Console

    monkeypatch.setattr(cli, "console", Console(width=250))
