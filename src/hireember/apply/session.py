"""GateSession: the single choke point for one ticket's apply run.

The agent asks it before every field it fills, every stop and every submit. It decides
from the answer bank and profile, blocks the ticket and queues a human item for every
stop, writes the attempt log, and records submit and outcome.
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from hireember import answers, config, tickets
from hireember.apply import attempts, limits

REASON_ACCOUNT = "account needed"
REASON_CAPTCHA = "captcha"
REASON_IDENTITY = "identity check"
REASON_VIDEO = "video or biometric"
REASON_REVIEW = "review before submit"
REASON_MANUAL = "manual site"
REASON_OUTCOME = "outcome unknown"
REASON_RECOVERED = "recovered after interrupted run"
REASON_NO_RESULT = "agent finished without a result"
REASON_CLOSED_DEFAULT = "closed by employer page"
STOP_REASONS = (REASON_ACCOUNT, REASON_CAPTCHA, REASON_IDENTITY, REASON_VIDEO)
INJECTION_LOG_KIND = "injected instruction ignored"

# normalized question -> (profile section, key)
_PROFILE_FIELDS: dict[str, tuple[str, str]] = {
    "full name": ("personal", "full_name"),
    "name": ("personal", "full_name"),
    "your name": ("personal", "full_name"),
    "legal name": ("personal", "full_name"),
    "email": ("personal", "email"),
    "email address": ("personal", "email"),
    "phone": ("personal", "phone"),
    "phone number": ("personal", "phone"),
    "mobile phone": ("personal", "phone"),
}

_INJECTION = re.compile(
    r"ignore\s+(?:all\s+|any\s+|the\s+)*(?:previous|prior|above|earlier)\s+(?:instructions|rules|prompts?)"
    r"|disregard|you\s+must\s+now|system\s+prompt|\bact\s+as\b|new\s+instructions"
    r"|forget\s+(?:all|your|everything)",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


class SessionError(Exception):
    """The session was used in a way that is not allowed."""


def queue_hand_off(conn: sqlite3.Connection, ticket_id: int, kind: str, page_link: str = "") -> int:
    """Block the ticket with ``kind`` and open (or reuse) its queue item; return the item id."""
    tickets.set_status(conn, ticket_id, "blocked for human", reason=kind)
    row = conn.execute(
        "SELECT id FROM queue_items WHERE ticket_id = ? AND kind = ? AND resolved_at IS NULL "
        "ORDER BY id LIMIT 1", (ticket_id, kind)).fetchone()
    if row:
        conn.execute("UPDATE queue_items SET page_link = ? WHERE id = ?", (page_link, row[0]))
        conn.commit()
        return row[0]
    company = conn.execute(
        "SELECT COALESCE(c.name, j.site, '') FROM tickets t JOIN jobs j ON j.url = t.job_url "
        "LEFT JOIN companies c ON c.id = j.company_id WHERE t.id = ?", (ticket_id,)).fetchone()
    cur = conn.execute(
        "INSERT INTO queue_items (ticket_id, kind, reason, page_link, question_text) "
        "VALUES (?, ?, ?, ?, ?)", (ticket_id, kind, kind, page_link, company[0] if company else ""))
    conn.commit()
    return cur.lastrowid


@dataclass
class FieldDecision:
    action: str            # "fill" or "stop"
    value: str | None
    source: str            # "answer:<id>", "profile:<key>", or "" when stopping
    reason: str            # "" when fill; else the ticket status_reason set by the stop
    queue_item_id: int | None


class GateSession:
    def __init__(self, conn: sqlite3.Connection, ticket_id: int, *,
                 review_before_submit: bool | None = None, attempt: int | None = None) -> None:
        self.conn = conn
        self.ticket_id = ticket_id
        try:
            ticket = tickets.get_ticket(conn, ticket_id)
        except tickets.TicketNotFoundError as e:
            raise SessionError(str(e)) from e
        self.attempt = attempt if attempt is not None else attempts.start_attempt(conn, ticket_id)
        self.state = "open"
        if review_before_submit is None:
            review_before_submit = (tickets.get_setting(conn, "review_before_submit") or "").strip().lower() == "true"
        self._review = review_before_submit
        self._noted: set[str] = set()
        self.resume_from: str | None = ticket.get("resume_link") or None
        if self.resume_from and not any(
                r["kind"] == "resume" and r["attempt"] == self.attempt and r["detail"] == self.resume_from
                for r in attempts.get_log(conn, ticket_id)):
            self._log("resume", detail=self.resume_from)

    # -- helpers ------------------------------------------------------------

    def _log(self, kind: str, field: str = "", source: str = "", detail: str = "") -> None:
        attempts.log_step(self.conn, self.ticket_id, self.attempt, kind, field, source, detail)

    def _check_not_closed(self) -> None:
        if self.state == "closed":
            raise SessionError(f"Ticket {self.ticket_id} is closed.")

    def _queue_stop(self, kind: str, page_link: str) -> int:
        item_id = queue_hand_off(self.conn, self.ticket_id, kind, page_link)
        self.state = "blocked"
        return item_id

    def _profile_value(self, question: str) -> tuple[str, str] | None:
        entry = _PROFILE_FIELDS.get(answers.normalize_question(question))
        if entry is None:
            return None
        try:
            profile = config.load_profile()
        except (FileNotFoundError, ValueError):
            return None
        value = (profile.get(entry[0]) or {}).get(entry[1])
        if not value or not str(value).strip():
            return None
        return str(value), f"profile:{entry[1]}"

    def _stop_field(self, question: str, kind: str, item_id: int | None = None) -> FieldDecision:
        self._log("stop", field=question)
        self.state = "blocked"
        return FieldDecision("stop", None, "", kind, item_id)

    @property
    def review(self) -> bool:
        """Whether review before submit is on for this session."""
        return bool(self._review)

    def refresh_state(self) -> str:
        """Adopt the outcome another process (the gate server) wrote to the ticket."""
        ticket = tickets.get_ticket(self.conn, self.ticket_id)
        if ticket["status"] == "applied":
            self.state = "submitted"
        elif ticket["status"] == "closed":
            self.state = "closed"
        elif ticket["status"] == "blocked for human":
            self.state = "blocked"
        elif ticket["submitted_at"] and self.state == "open":
            self.state = "submit_pressed"
        return self.state

    # -- the agent's questions ----------------------------------------------

    def answer_field(self, question: str, field_type: str = "text") -> FieldDecision:
        self._check_not_closed()
        if field_type == "password" or answers.is_sensitive(question):
            tickets.set_status(self.conn, self.ticket_id, "blocked for human",
                               reason=answers.KIND_SENSITIVE)
            item_id = answers.queue_question(self.conn, self.ticket_id, answers.KIND_SENSITIVE, question)
            return self._stop_field(question, answers.KIND_SENSITIVE, item_id)
        found = self._profile_value(question)
        if found:
            self._log("fill", question, found[1], found[0])
            return FieldDecision("fill", found[0], found[1], "", None)
        result = answers.match_answer(self.conn, self.ticket_id, question)
        if result.status == "answered":
            source = f"answer:{result.answer_id}"
            self._log("fill", question, source, result.answer or "")
            return FieldDecision("fill", result.answer, source, "", None)
        kind = {"unknown": answers.KIND_UNKNOWN, "conflict": answers.KIND_CONFLICT,
                "sensitive": answers.KIND_SENSITIVE}[result.status]
        return self._stop_field(question, kind, result.queue_item_id)

    def resume_path(self) -> str:
        path = tickets.get_ticket(self.conn, self.ticket_id).get("tailored_resume_path")
        if not path:
            raise SessionError(f"No tailored resume for ticket {self.ticket_id}.")
        pdf = Path(path).with_suffix(".pdf").resolve()
        self._log("upload", field=pdf.name)
        return str(pdf)

    def stop(self, reason: str, page_link: str = "") -> None:
        if reason not in STOP_REASONS:
            raise ValueError(f"Invalid stop reason {reason!r}. Allowed: {', '.join(STOP_REASONS)}.")
        self._check_not_closed()
        self._queue_stop(reason, page_link)
        self._log("stop", detail=reason)

    def note_page_text(self, text: str) -> bool:
        """Report page text that reads like an instruction. It changes no state or answer."""
        found = False
        for sentence in _SENTENCES.split(text or ""):
            sentence = sentence.strip()
            if sentence and _INJECTION.search(sentence):
                found = True
                if sentence not in self._noted:
                    self._noted.add(sentence)
                    self._log(INJECTION_LOG_KIND, detail=sentence)
        return found

    def before_submit(self) -> str:
        self._check_not_closed()
        marker = f"skip_review_once:{self.ticket_id}"
        skip_once = tickets.get_setting(self.conn, marker) == "1"
        if skip_once:
            self.conn.execute("DELETE FROM settings WHERE key = ?", (marker,))
            self.conn.commit()
        if self._review and not skip_once:
            self._queue_stop(REASON_REVIEW, "")
            return "stop"
        return "submit"

    def submit_pressed(self) -> None:
        self._check_not_closed()
        self.conn.execute("UPDATE tickets SET submitted_at = ? WHERE id = ?",
                          (tickets._now(), self.ticket_id))
        self.conn.commit()
        self.state = "submit_pressed"
        self._log("submit")

    def submitted(self, confirmation_link: str | None = None) -> None:
        self._check_not_closed()
        link = (confirmation_link or "").strip()
        self.conn.execute(
            "UPDATE tickets SET submitted_at = COALESCE(submitted_at, ?), confirmation_link = ?, "
            "unverified = ?, session_link = NULL, resume_link = NULL WHERE id = ?",
            (tickets._now(), link or None, 0 if link else 1, self.ticket_id))
        self.conn.commit()
        tickets.set_status(self.conn, self.ticket_id, "applied", reason="confirmed" if link else "unverified",
                           link=link or None, link_kind="confirmation" if link else None)
        limits.record_submission(self.conn, self.ticket_id)
        self.state = "submitted"

    def closed(self, reason: str = "") -> None:
        why = (reason or "").strip() or REASON_CLOSED_DEFAULT
        self.conn.execute("UPDATE tickets SET session_link = NULL, resume_link = NULL WHERE id = ?",
                          (self.ticket_id,))
        self.conn.commit()
        tickets.set_status(self.conn, self.ticket_id, "closed", reason=why)
        self.state = "closed"
