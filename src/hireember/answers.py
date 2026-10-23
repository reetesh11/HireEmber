"""Answer bank: stored answers, browser-free matching and the human question queue."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from hireember import tickets
from hireember.tickets import normalize_text

KIND_UNKNOWN = "unknown question"
KIND_CONFLICT = "conflicting answers"
KIND_SENSITIVE = "sensitive question"

SOURCES = ("profile", "user", "import")

READY_KINDS = (
    "account needed", "captcha", "identity check", "video or biometric",
    "review before submit", "manual site", "outcome unknown",
)

_SENSITIVE = re.compile(
    r"\b(password|passcode|token|api key|card number|credit card|debit card|cvv|cvc|"
    r"bank account|routing number|iban|ssn|social security|social insurance|passport|"
    r"national id|government id|tax id|driver s? ?licen[cs]e)\b"
)


class SensitiveQuestionError(ValueError):
    """The question asks for a password, token, payment detail or government ID."""


class AnswerError(ValueError):
    """A stored answer could not be changed."""


class QueueError(Exception):
    """A queue item could not be answered."""


@dataclass
class AnswerResult:
    status: str  # "answered", "unknown", "conflict" or "sensitive"
    answer: str | None = None
    queue_item_id: int | None = None
    answer_id: int | None = None


@dataclass
class QueueAnswerResult:
    saved: bool
    ticket_id: int | None
    message: str


def normalize_question(text: str) -> str:
    return normalize_text(text)


def is_sensitive(question: str) -> bool:
    return bool(_SENSITIVE.search(normalize_question(question)))


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(zip(r.keys(), tuple(r))) for r in conn.execute(sql, params).fetchall()]


# -- answer bank ------------------------------------------------------------

def save_answer(conn: sqlite3.Connection, question: str, answer: str, source: str = "user",
                *, replace: bool = True) -> int:
    """Store an answer; with ``replace`` an existing entry for the same key is updated."""
    if source not in SOURCES:
        raise ValueError(f"Invalid source {source!r}. Allowed sources: {', '.join(SOURCES)}.")
    if is_sensitive(question):
        raise SensitiveQuestionError(
            "Passwords, tokens, payment details and government IDs are never stored.")
    if not (answer or "").strip():
        raise ValueError("Answer cannot be empty.")
    key = normalize_question(question)
    if replace:
        row = conn.execute("SELECT id FROM answers WHERE normalized_key = ? ORDER BY id LIMIT 1",
                           (key,)).fetchone()
        if row:
            conn.execute("UPDATE answers SET answer = ?, source = ? WHERE id = ?",
                         (answer, source, row[0]))
            conn.commit()
            return row[0]
    cur = conn.execute(
        "INSERT INTO answers (question_text, normalized_key, answer, source, times_used, "
        "last_used_at) VALUES (?, ?, ?, ?, 0, NULL)",
        (question, key, answer, source),
    )
    conn.commit()
    return cur.lastrowid


def list_answers(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT id, question_text, normalized_key, answer, source, times_used, "
                       "last_used_at FROM answers ORDER BY id")


def _check_answer(question: str, answer: str) -> None:
    if is_sensitive(question):
        raise SensitiveQuestionError(
            "Passwords, tokens, payment details and government IDs are never stored.")
    if not (answer or "").strip():
        raise AnswerError("Answer cannot be empty.")


def _answer_row(conn: sqlite3.Connection, answer_id: int) -> dict:
    rows = _rows(conn, "SELECT id, question_text, answer, times_used, last_used_at "
                       "FROM answers WHERE id = ?", (answer_id,))
    if not rows:
        raise AnswerError(f"Answer {answer_id} not found.")
    return rows[0]


def update_answer(conn: sqlite3.Connection, answer_id: int, question: str, answer: str) -> None:
    """Change the question text and answer of a stored entry (source is kept)."""
    _answer_row(conn, answer_id)
    _check_answer(question, answer)
    conn.execute("UPDATE answers SET question_text = ?, normalized_key = ?, answer = ? WHERE id = ?",
                 (question, normalize_question(question), answer, answer_id))
    conn.commit()


def delete_answer(conn: sqlite3.Connection, answer_id: int) -> None:
    """Remove a stored answer; queue items and tickets are untouched."""
    _answer_row(conn, answer_id)
    conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
    conn.commit()


def merge_answers(conn: sqlite3.Connection, keep_id: int, remove_id: int, *,
                  question: str | None = None, answer: str | None = None) -> int:
    """Fold ``remove_id`` into ``keep_id`` using the chosen text; usage counts are added."""
    if keep_id == remove_id:
        raise AnswerError("Choose two different answers to merge.")
    keep = _answer_row(conn, keep_id)
    gone = _answer_row(conn, remove_id)
    question = keep["question_text"] if question is None else question
    answer = keep["answer"] if answer is None else answer
    _check_answer(question, answer)
    last = max((v for v in (keep["last_used_at"], gone["last_used_at"]) if v), default=None)
    try:
        conn.execute(
            "UPDATE answers SET question_text = ?, normalized_key = ?, answer = ?, "
            "times_used = ?, last_used_at = ? WHERE id = ?",
            (question, normalize_question(question), answer,
             (keep["times_used"] or 0) + (gone["times_used"] or 0), last, keep_id))
        conn.execute("DELETE FROM answers WHERE id = ?", (remove_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return keep_id


# -- queue ------------------------------------------------------------------

def queue_question(conn: sqlite3.Connection, ticket_id: int, kind: str, question: str) -> int:
    """Add an open queue item for the question, or reuse the open one for the same question."""
    key = normalize_question(question)
    for item in _rows(conn, "SELECT id, question_text FROM queue_items "
                            "WHERE ticket_id = ? AND resolved_at IS NULL ORDER BY id", (ticket_id,)):
        if normalize_question(item["question_text"]) == key:
            return item["id"]
    cur = conn.execute(
        "INSERT INTO queue_items (ticket_id, kind, reason, question_text) VALUES (?, ?, ?, ?)",
        (ticket_id, kind, kind, question),
    )
    conn.commit()
    return cur.lastrowid


def list_queue(conn: sqlite3.Connection, include_resolved: bool = False) -> list[dict]:
    where = "" if include_resolved else "WHERE resolved_at IS NULL "
    return _rows(conn, "SELECT q.id, q.ticket_id, q.kind, q.reason, q.page_link, q.question_text, "
                       "q.resolved_at, COALESCE(c.name, j.site, '') AS company "
                       "FROM queue_items q LEFT JOIN tickets t ON t.id = q.ticket_id "
                       "LEFT JOIN jobs j ON j.url = t.job_url "
                       "LEFT JOIN companies c ON c.id = j.company_id "
                       f"{where.replace('resolved_at', 'q.resolved_at')}"
                       "ORDER BY (q.resolved_at IS NOT NULL), q.id")


def _block(conn: sqlite3.Connection, ticket_id: int, kind: str, question: str, status: str) -> AnswerResult:
    tickets.set_status(conn, ticket_id, "blocked for human", reason=kind)
    return AnswerResult(status, None, queue_question(conn, ticket_id, kind, question))


def match_answer(conn: sqlite3.Connection, ticket_id: int, question: str) -> AnswerResult:
    """Look the question up in the bank; block the ticket and queue it when it cannot be answered."""
    if is_sensitive(question):
        return _block(conn, ticket_id, KIND_SENSITIVE, question, "sensitive")
    matches = _rows(conn, "SELECT id, answer FROM answers WHERE normalized_key = ? ORDER BY id",
                    (normalize_question(question),))
    if not matches:
        return _block(conn, ticket_id, KIND_UNKNOWN, question, "unknown")
    if len({m["answer"].strip().casefold() for m in matches}) > 1:
        return _block(conn, ticket_id, KIND_CONFLICT, question, "conflict")
    first = matches[0]
    conn.execute("UPDATE answers SET times_used = COALESCE(times_used, 0) + 1, last_used_at = ? "
                 "WHERE id = ?", (tickets._now(), first["id"]))
    conn.commit()
    return AnswerResult("answered", first["answer"], None, first["id"])


def answer_queue_item(conn: sqlite3.Connection, item_id: int, answer: str) -> QueueAnswerResult:
    """Store a human answer for a queued question, resolve the item and resume its ticket."""
    if not (answer or "").strip():
        raise QueueError("Answer cannot be empty.")
    rows = _rows(conn, "SELECT id, ticket_id, kind, question_text FROM queue_items "
                       "WHERE id = ? AND resolved_at IS NULL", (item_id,))
    if not rows:
        raise QueueError(f"Queue item {item_id} not found or already resolved.")
    item = rows[0]
    ticket_id = item["ticket_id"]
    if item["kind"] in READY_KINDS:
        raise QueueError('Use "queue ready" for this item.')
    if item["kind"] == KIND_SENSITIVE:
        conn.execute("UPDATE queue_items SET resolved_at = ? WHERE id = ?", (tickets._now(), item_id))
        conn.commit()
        return QueueAnswerResult(
            False, ticket_id,
            "Not saved: passwords, tokens, payment details and government IDs are never stored. "
            f"Ticket {ticket_id} stays blocked for human.")
    save_answer(conn, item["question_text"], answer, "user")
    conn.execute("UPDATE queue_items SET resolved_at = ? WHERE id = ?", (tickets._now(), item_id))
    conn.commit()
    if ticket_id is not None and tickets.get_ticket(conn, ticket_id)["status"] == "blocked for human":
        tickets.set_status(conn, ticket_id, "pending", actor="user", reason="answered queued question")
    return QueueAnswerResult(True, ticket_id, f"Answer saved. Ticket {ticket_id} is ready to resume.")


def ready_queue_item(conn: sqlite3.Connection, item_id: int) -> QueueAnswerResult:
    """Resolve a non-question item (account, captcha, review...) and return its ticket to pending."""
    rows = _rows(conn, "SELECT id, ticket_id, kind, page_link FROM queue_items "
                       "WHERE id = ? AND resolved_at IS NULL", (item_id,))
    if not rows:
        raise QueueError(f"Queue item {item_id} not found or already resolved.")
    item = rows[0]
    if item["kind"] not in READY_KINDS:
        raise QueueError('Use "queue answer" for this item.')
    ticket_id = item["ticket_id"]
    conn.execute("UPDATE queue_items SET resolved_at = ? WHERE id = ?", (tickets._now(), item_id))
    if ticket_id is not None:
        conn.execute("UPDATE tickets SET resume_link = ?, not_before = NULL, "
                     "submitted_at = CASE WHEN ? = 1 THEN NULL ELSE submitted_at END WHERE id = ?",
                     (item["page_link"] or None, 1 if item["kind"] == "outcome unknown" else 0,
                      ticket_id))
    conn.commit()
    if ticket_id is not None and item["kind"] == "review before submit":
        tickets.set_setting(conn, f"skip_review_once:{ticket_id}", "1")
    if ticket_id is not None and tickets.get_ticket(conn, ticket_id)["status"] == "blocked for human":
        tickets.set_status(conn, ticket_id, "pending", actor="user", reason="ready")
    return QueueAnswerResult(True, ticket_id, f"Ticket {ticket_id} is ready to resume.")
