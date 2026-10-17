"""Ticket data layer: statuses, history, scoring tickets and duplicate checks."""

import re
import sqlite3
from datetime import datetime, timezone

ALLOWED_STATUSES: tuple[str, ...] = (
    "pending", "started", "applying", "blocked for human", "applied", "skipped", "closed",
)


class TicketError(Exception):
    """Base class for ticket errors."""


class InvalidStatusError(TicketError, ValueError):
    """A status outside ALLOWED_STATUSES was requested."""

    def __init__(self, value: object):
        super().__init__(
            f"Invalid status {value!r}. Allowed statuses: {', '.join(ALLOWED_STATUSES)}."
        )


class TicketNotFoundError(TicketError):
    """No ticket with the given id."""

    def __init__(self, ticket_id: int):
        super().__init__(f"Ticket {ticket_id} not found.")


class DuplicateTicketError(TicketError):
    """The ticket duplicates a ticket that is already in progress or done."""

    def __init__(self, ticket_id: int, duplicate_of: int):
        self.ticket_id = ticket_id
        self.duplicate_of = duplicate_of
        super().__init__(f"Ticket {ticket_id} is a duplicate of ticket {duplicate_of}; not started.")


class OverrideReasonError(TicketError):
    """An override was requested without a reason."""

    def __init__(self):
        super().__init__("An override needs a reason.")


_PUNCT = re.compile(r"[^\w\s]|_", re.UNICODE)


def normalize_text(value: str | None) -> str:
    """Lowercase, replace punctuation with a space, collapse whitespace, trim."""
    if not value:
        return ""
    return " ".join(_PUNCT.sub(" ", str(value).lower()).split())


DEFAULT_THRESHOLD = 7
_ACTORS = ("system", "user")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# -- companies and settings -------------------------------------------------

def get_or_create_company(conn: sqlite3.Connection, name: str) -> int:
    """Return the id of the company called ``name`` (case-insensitive), creating it if missing."""
    clean = (name or "").strip()
    row = conn.execute(
        "SELECT id FROM companies WHERE lower(trim(name)) = ? ORDER BY id LIMIT 1",
        (clean.lower(),),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO companies (name) VALUES (?)", (clean,))
    conn.commit()
    return cur.lastrowid


def set_job_company(conn: sqlite3.Connection, url: str, name: str) -> int:
    """Link a job to a company by name; return the company id."""
    company_id = get_or_create_company(conn, name)
    conn.execute("UPDATE jobs SET company_id = ? WHERE url = ?", (company_id, url))
    conn.commit()
    return company_id


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Insert or update a settings row."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_threshold(conn: sqlite3.Connection) -> int:
    """Score threshold from settings key ``score_threshold``; 7 if missing or not a number."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'score_threshold'").fetchone()
    try:
        return int(str(row[0]).strip()) if row and row[0] is not None else DEFAULT_THRESHOLD
    except ValueError:
        return DEFAULT_THRESHOLD


# -- tickets ----------------------------------------------------------------

def _add_event(conn, ticket_id, status, actor, reason, link=None, link_kind=None, when=None) -> None:
    conn.execute(
        "INSERT INTO ticket_events (ticket_id, status, actor, reason, link, link_kind, time) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, status, actor, reason or "", link, link_kind, when or _now()),
    )


def _ensure_ticket(conn: sqlite3.Connection, url: str, commit: bool) -> int:
    job = conn.execute(
        "SELECT fit_score, score_reasoning FROM jobs WHERE url = ?", (url,)
    ).fetchone()
    if job is None:
        raise TicketError(f"Job {url} not found.")
    score = job[0]
    if score is None:
        raise TicketError(f"Job {url} has no score.")
    existing = conn.execute("SELECT id FROM tickets WHERE job_url = ?", (url,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE tickets SET score = ?, score_reason = ? WHERE id = ?",
            (score, job[1], existing[0]),
        )
        if commit:
            conn.commit()
        return existing[0]
    threshold = get_threshold(conn)
    if score >= threshold:
        status, reason = "pending", f"score {score} meets threshold {threshold}"
    else:
        status, reason = "skipped", f"score {score} below threshold {threshold}"
    now = _now()
    try:
        cur = conn.execute(
            "INSERT INTO tickets (job_url, status, status_reason, score, score_reason, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (url, status, reason, score, job[1], now, now),
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return conn.execute("SELECT id FROM tickets WHERE job_url = ?", (url,)).fetchone()[0]
    _add_event(conn, cur.lastrowid, status, "system", reason, when=now)
    if commit:
        conn.commit()
    return cur.lastrowid


def ensure_ticket(conn: sqlite3.Connection, url: str) -> int:
    """Ensure one ticket exists for a scored job and return its id."""
    return _ensure_ticket(conn, url, True)


def set_job_score(conn: sqlite3.Connection, url: str, score: int, reasoning: str = "",
                  *, commit: bool = True) -> int:
    """Store a fit score on the job and ensure its ticket; return the ticket id.

    ``commit=False`` leaves the transaction open so a caller can batch many scores.
    """
    conn.execute(
        "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
        (score, reasoning, _now(), url),
    )
    return _ensure_ticket(conn, url, commit)


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> dict:
    """Return a ticket as a dict; raise TicketNotFoundError if it does not exist."""
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise TicketNotFoundError(ticket_id)
    return dict(zip(row.keys(), tuple(row)))


def get_ticket_by_url(conn: sqlite3.Connection, url: str) -> dict | None:
    """Return the ticket for a job URL, or None."""
    row = conn.execute("SELECT * FROM tickets WHERE job_url = ?", (url,)).fetchone()
    return dict(zip(row.keys(), tuple(row))) if row else None


def get_history(conn: sqlite3.Connection, ticket_id: int) -> list[dict]:
    """Return the ticket's events, oldest first."""
    rows = conn.execute(
        "SELECT id, ticket_id, status, actor, reason, link, link_kind, time "
        "FROM ticket_events WHERE ticket_id = ? ORDER BY id",
        (ticket_id,),
    ).fetchall()
    return [dict(zip(r.keys(), tuple(r))) for r in rows]


def set_status(conn: sqlite3.Connection, ticket_id: int, status: str, *,
               actor: str = "system", reason: str = "", link: str | None = None,
               link_kind: str | None = None, override_reason: str | None = None) -> None:
    """Move a ticket to ``status`` and write one history event.

    Asking for the current status is a no-op.
    """
    if status not in ALLOWED_STATUSES:
        raise InvalidStatusError(status)
    if actor not in _ACTORS:
        raise ValueError(f"Invalid actor {actor!r}. Allowed actors: {', '.join(_ACTORS)}.")
    ticket = get_ticket(conn, ticket_id)
    if ticket["status"] == status:
        return
    _write_status(conn, ticket_id, status, actor, reason, link, link_kind)
    conn.commit()


def _write_status(conn, ticket_id, status, actor, reason, link, link_kind) -> None:
    now = _now()
    conn.execute(
        "UPDATE tickets SET status = ?, status_reason = ?, updated_at = ? WHERE id = ?",
        (status, reason or "", now, ticket_id),
    )
    _add_event(conn, ticket_id, status, actor, reason, link, link_kind, now)
