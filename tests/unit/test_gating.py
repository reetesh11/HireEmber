"""Gating: score, threshold, tailor (implementation tests with fake LLM clients)."""

import json

import pytest

from hireember import config, gating
from hireember.database import close_connection, init_db, store_jobs
from hireember.resumes import add_resume
from hireember.scoring import tailor
from hireember.tickets import get_ticket

PROFILE = {
    "skills_boundary": {"languages": ["Python"]},
    "resume_facts": {"preserved_companies": ["Company A"], "preserved_projects": ["Project X"],
                     "preserved_school": "Your University", "real_metrics": []},
}
GOOD = {
    "title": "Dev", "summary": "Builds services.", "skills": {"Languages": "Python"},
    "experience": [{"header": "Company A", "subtitle": "2020", "bullets": ["Built APIs."]}],
    "projects": [{"header": "Project X", "subtitle": "Python", "bullets": ["Parsed logs."]}],
    "education": "Your University | BSc",
}


class Client:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, messages, max_tokens=None, temperature=None):
        return self.reply


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    config.ensure_dirs()
    store_jobs(c, [{"url": "u1", "title": "Python Dev", "company": "Acme"}], "S", "t")
    c.execute("UPDATE jobs SET full_description = 'desc'")
    c.commit()
    monkeypatch.setattr("hireember.scoring.scorer.get_client",
                        lambda *a, **k: Client("SCORE: 9\nKEYWORDS: a\nREASONING: Great."))
    monkeypatch.setattr("hireember.scoring.tailor.get_client", lambda *a, **k: Client(json.dumps(GOOD)))
    monkeypatch.setattr("hireember.scoring.cover_letter.get_client",
                        lambda *a, **k: Client("Dear Hiring Manager,\n\nHello."))
    yield c
    close_connection(db)


def _resume(conn, tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    return add_resume(conn, f, "Base", "python")


def test_blocked_without_resume_is_rescored_after_adding_one(conn, tmp_path):
    first = gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    assert (first.status, first.reason) == ("blocked for human", "no base resume")
    rid = _resume(conn, tmp_path)
    again = gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    assert again.ticket_id == first.ticket_id and again.status == "pending" and again.resume_id == rid


def test_tailor_ticket_only_runs_once(conn, tmp_path):
    _resume(conn, tmp_path)
    done = gating.process_job(conn, "u1", profile=PROFILE, validation_mode="lenient")
    assert done.tailored_resume_path.endswith(".pdf") and f"ticket{done.ticket_id}_" in done.tailored_resume_path
    before = get_ticket(conn, done.ticket_id)
    gating.tailor_ticket(conn, done.ticket_id, profile=PROFILE, validation_mode="lenient")
    assert get_ticket(conn, done.ticket_id) == before
    job = conn.execute("SELECT tailored_resume_path, cover_letter_path FROM jobs").fetchone()
    assert job[0].endswith(".txt") and job[1].endswith("_CL.txt")


def test_run_tailoring_counts(conn, tmp_path, monkeypatch):
    _resume(conn, tmp_path)
    gating.score_job_for_ticket(conn, "u1", profile=PROFILE)
    monkeypatch.setattr(tailor, "load_profile", lambda: PROFILE)
    monkeypatch.setattr(tailor, "get_connection", lambda: conn)
    result = tailor.run_tailoring(validation_mode="lenient")
    assert (result["approved"], result["failed"], result["errors"]) == (1, 0, 0)
