"""Score and tailor gating: pick a base resume, score, apply the threshold, tailor and validate."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from hireember import tickets
from hireember.config import load_profile
from hireember.resumes import ResumeError, choose_resume, get_resume_text
from hireember.scoring import scorer

log = logging.getLogger(__name__)


@dataclass
class GateResult:
    ticket_id: int
    status: str
    reason: str
    score: int | None = None
    resume_id: int | None = None
    tailored_resume_path: str | None = None
    cover_letter_path: str | None = None


def _profile(profile: dict | None) -> dict:
    if profile is not None:
        return profile
    try:
        return load_profile()
    except FileNotFoundError:
        return {}


def _result(conn: sqlite3.Connection, ticket_id: int) -> GateResult:
    t = tickets.get_ticket(conn, ticket_id)
    return GateResult(ticket_id, t["status"], t["status_reason"] or "", t["score"], t["resume_id"],
                      t["tailored_resume_path"], t["cover_letter_path"])


def _block(conn: sqlite3.Connection, url: str, reason: str, resume_id: int | None) -> GateResult:
    ticket_id = tickets.open_ticket(conn, url, "blocked for human", reason)
    tickets.set_status(conn, ticket_id, "blocked for human", reason=reason)
    if resume_id is not None:
        tickets.set_ticket_resume(conn, ticket_id, resume_id)
    return _result(conn, ticket_id)


def score_job_for_ticket(conn: sqlite3.Connection, url: str, *, profile: dict | None = None) -> GateResult:
    """Choose a base resume, score the job and create or update its ticket by the threshold."""
    profile = _profile(profile)
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if row is None:
        raise tickets.TicketError(f"Job {url} not found.")
    job = dict(zip(row.keys(), tuple(row)))

    resume_id = choose_resume(conn, job)
    if resume_id is None:
        return _block(conn, url, "no base resume", None)
    try:
        resume_text = get_resume_text(conn, resume_id)
    except ResumeError as e:
        return _block(conn, url, str(e), resume_id)

    result = scorer.score_job(resume_text, job, profile)
    if not result["score"]:
        reason = result["reasoning"] or ""
        if not reason.startswith("LLM error"):
            reason = "LLM error: no score in the response"
        return _block(conn, url, reason, resume_id)

    prior = tickets.get_ticket_by_url(conn, url)
    ticket_id = tickets.set_job_score(conn, url, result["score"], result["reasoning"] or "no reason given")
    tickets.set_ticket_resume(conn, ticket_id, resume_id)
    if prior and prior["score"] is None and prior["status"] == "blocked for human":
        # An earlier attempt blocked before scoring; the score now decides the status.
        threshold = tickets.get_threshold(conn)
        if result["score"] >= threshold:
            tickets.set_status(conn, ticket_id, "pending", reason=f"score {result['score']} meets threshold {threshold}")
        else:
            tickets.set_status(conn, ticket_id, "skipped",
                               reason=f"score {result['score']} below threshold {threshold}")
    return _result(conn, ticket_id)
