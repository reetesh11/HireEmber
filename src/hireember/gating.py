"""Score and tailor gating: pick a base resume, score, apply the threshold, tailor and validate."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass

from hireember import tickets, usage
from hireember.config import COVER_LETTER_DIR, TAILORED_DIR, load_profile
from hireember.location import location_skip_reason
from hireember.resumes import ResumeError, choose_resume, get_resume_text
from hireember.scoring import cover_letter, scorer, tailor
from hireember.scoring.pdf import convert_to_pdf

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
    """Skip jobs outside the target locations; otherwise choose a base resume, score the job and
    create or update its ticket by the threshold."""
    profile = _profile(profile)
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if row is None:
        raise tickets.TicketError(f"Job {url} not found.")
    job = dict(zip(row.keys(), tuple(row)))

    existing = tickets.get_ticket_by_url(conn, url)
    if not (existing and existing["score"] is not None):
        reason = location_skip_reason(job.get("location"), profile)
        if reason:
            ticket_id = tickets.open_ticket(conn, url, "skipped", reason)
            tickets.set_status(conn, ticket_id, "skipped", reason=reason)
            return _result(conn, ticket_id)

    resume_id = choose_resume(conn, job)
    if resume_id is None:
        return _block(conn, url, "no base resume", None)
    try:
        resume_text = get_resume_text(conn, resume_id)
    except ResumeError as e:
        return _block(conn, url, str(e), resume_id)

    with usage.collect() as spent:
        result = scorer.score_job(resume_text, job, profile)
    if not result["score"]:
        reason = result["reasoning"] or ""
        if not reason.startswith("LLM error"):
            reason = "LLM error: no score in the response"
        blocked = _block(conn, url, reason, resume_id)
        usage.record_collected(conn, blocked.ticket_id, "scoring", spent)
        return blocked

    prior = tickets.get_ticket_by_url(conn, url)
    ticket_id = tickets.set_job_score(conn, url, result["score"], result["reasoning"] or "no reason given")
    usage.record_collected(conn, ticket_id, "scoring", spent)
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


def _slug(title: str) -> str:
    return re.sub(r"[^\w\s-]", "", title or "")[:50].strip().replace(" ", "_") or "job"


def _fail_reason(report: dict) -> str:
    errors = (report.get("validator") or {}).get("errors") or []
    return f"validation failed: {errors[0] if errors else 'output was not valid JSON'}"


def tailor_ticket(conn: sqlite3.Connection, ticket_id: int, *, profile: dict | None = None,
                  validation_mode: str = "normal", max_retries: int = 3) -> GateResult:
    """Tailor the resume and write the cover letter for a pending ticket; block it when validation fails.

    A ticket that is not pending, has no base resume, or already has files is returned unchanged.
    """
    ticket = tickets.get_ticket(conn, ticket_id)
    if (ticket["status"] != "pending" or not ticket["resume_id"]
            or ticket["tailored_resume_path"] or ticket["cover_letter_path"]):
        return _result(conn, ticket_id)
    profile = _profile(profile)
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (ticket["job_url"],)).fetchone()
    job = dict(zip(row.keys(), tuple(row)))

    def block(reason: str) -> GateResult:
        tickets.set_status(conn, ticket_id, "blocked for human", reason=reason)
        return _result(conn, ticket_id)

    try:
        resume_text = get_resume_text(conn, ticket["resume_id"])
    except ResumeError as e:
        return block(str(e))
    with usage.collect() as spent:
        try:
            tailored, report = tailor.tailor_resume(resume_text, job, profile,
                                                    max_retries=max_retries,
                                                    validation_mode=validation_mode)
            if report["status"] not in ("approved", "approved_with_judge_warning"):
                return block(_fail_reason(report))
            letter = cover_letter.generate_cover_letter(tailored, job, profile,
                                                        validation_mode=validation_mode)
        except Exception as e:
            log.error("Tailoring ticket %d failed: %s", ticket_id, e)
            return block(f"LLM error: {e}")
        finally:
            usage.record_collected(conn, ticket_id, "tailoring", spent)

    TAILORED_DIR.mkdir(parents=True, exist_ok=True)
    COVER_LETTER_DIR.mkdir(parents=True, exist_ok=True)
    name = f"ticket{ticket_id}_{_slug(job.get('title', ''))}"
    resume_txt = TAILORED_DIR / f"{name}.txt"
    resume_txt.write_text(tailored, encoding="utf-8")
    (TAILORED_DIR / f"{name}_REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    letter_txt = COVER_LETTER_DIR / f"{name}_CL.txt"
    letter_txt.write_text(letter, encoding="utf-8")
    resume_pdf = convert_to_pdf(resume_txt)
    letter_pdf = convert_to_pdf(letter_txt)
    tickets.set_ticket_files(conn, ticket_id, str(resume_pdf), str(letter_pdf))
    # The apply stage still reads the job row, so keep it in step with the ticket.
    now = tickets._now()
    conn.execute(
        "UPDATE jobs SET tailored_resume_path = ?, tailored_at = ?, cover_letter_path = ?, "
        "cover_letter_at = ?, tailor_attempts = COALESCE(tailor_attempts, 0) + 1, "
        "cover_attempts = COALESCE(cover_attempts, 0) + 1 WHERE url = ?",
        (str(resume_txt), now, str(letter_txt), now, ticket["job_url"]),
    )
    conn.commit()
    return _result(conn, ticket_id)


def process_job(conn: sqlite3.Connection, url: str, *, profile: dict | None = None,
                validation_mode: str = "normal") -> GateResult:
    """Score a job, then tailor it when its ticket is pending."""
    profile = _profile(profile)
    result = score_job_for_ticket(conn, url, profile=profile)
    if result.status != "pending":
        return result
    return tailor_ticket(conn, result.ticket_id, profile=profile, validation_mode=validation_mode)
