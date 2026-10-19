"""apply_ticket: one apply attempt with every safety check done in Python, not in the prompt."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from hireember import tickets
from hireember.apply import attempts, limits
from hireember.apply.session import (
    REASON_MANUAL,
    REASON_NO_RESULT,
    REASON_OUTCOME,
    REASON_RECOVERED,
    GateSession,
    queue_hand_off,
)

REASON_INTERRUPTED = "interrupted before submit"


@dataclass
class ApplyOutcome:
    ticket_id: int
    result: str      # "applied", "blocked", "closed", "held", "duplicate", "interrupted", "skipped"
    reason: str
    session: GateSession | None


def _outcome(conn: sqlite3.Connection, ticket_id: int, result: str,
             session: GateSession | None = None) -> ApplyOutcome:
    return ApplyOutcome(ticket_id, result, tickets.get_ticket(conn, ticket_id)["status_reason"] or "",
                        session)


def _clear_session_link(conn: sqlite3.Connection, ticket_id: int) -> None:
    conn.execute("UPDATE tickets SET session_link = NULL WHERE id = ?", (ticket_id,))
    conn.commit()


def _block_unknown(conn: sqlite3.Connection, ticket_id: int) -> None:
    queue_hand_off(conn, ticket_id, REASON_OUTCOME)


def apply_ticket(conn: sqlite3.Connection, ticket_id: int,
                 agent: Callable[[GateSession], None], *,
                 review_before_submit: bool | None = None,
                 now: datetime | None = None,
                 session_link: str = "http://127.0.0.1:9222") -> ApplyOutcome:
    """Run one attempt on a ticket; the agent is called only if every check passes."""
    ticket = tickets.get_ticket(conn, ticket_id)
    status, reason = ticket["status"], ticket["status_reason"]
    if status in ("applied", "closed") or (status == "blocked for human" and reason != "ready"):
        return _outcome(conn, ticket_id, "skipped")

    if tickets.is_manual_company(conn, ticket_id):
        queue_hand_off(conn, ticket_id, REASON_MANUAL)
        return _outcome(conn, ticket_id, "blocked")

    if status in ("pending", "blocked for human"):
        try:
            tickets.set_status(conn, ticket_id, "started")
        except tickets.DuplicateTicketError:
            return _outcome(conn, ticket_id, "duplicate")

    result = limits.check_limits(conn, ticket_id, now)
    if not result.ok:
        limits.hold_ticket(conn, ticket_id, result)
        return _outcome(conn, ticket_id, "held")

    tickets.set_status(conn, ticket_id, "applying", link=session_link, link_kind="session")
    conn.execute("UPDATE tickets SET session_link = ? WHERE id = ?", (session_link, ticket_id))
    conn.commit()
    attempt = attempts.start_attempt(conn, ticket_id)
    attempts.log_step(conn, ticket_id, attempt, "start", detail=session_link)
    session = GateSession(conn, ticket_id, review_before_submit=review_before_submit, attempt=attempt)

    try:
        agent(session)
    except BaseException as exc:
        attempts.log_step(conn, ticket_id, attempt, "error", detail=f"{type(exc).__name__}: {exc}")
        _settle(conn, ticket_id, session, interrupted=True)
        if not isinstance(exc, Exception):
            raise
        return _outcome(conn, ticket_id, _result_for(session), session)
    _settle(conn, ticket_id, session, interrupted=False)
    return _outcome(conn, ticket_id, _result_for(session), session)


def _result_for(session: GateSession) -> str:
    return {"submitted": "applied", "blocked": "blocked", "closed": "closed",
            "submit_pressed": "blocked"}.get(session.state, "interrupted")


def _settle(conn: sqlite3.Connection, ticket_id: int, session: GateSession, *, interrupted: bool) -> None:
    """Put the ticket in its final state after the agent returned or raised."""
    if session.state in ("submitted", "blocked", "closed"):
        return
    if session.state == "submit_pressed":
        _block_unknown(conn, ticket_id)
        session.state = "blocked"
        return
    why = REASON_INTERRUPTED if interrupted else REASON_NO_RESULT
    tickets.set_status(conn, ticket_id, "pending", reason=why)
    _clear_session_link(conn, ticket_id)


def recover_stale_tickets(conn: sqlite3.Connection) -> list[int]:
    """Settle tickets left in ``applying`` by a run that died; return their ids."""
    rows = conn.execute("SELECT id, submitted_at FROM tickets WHERE status = 'applying' ORDER BY id").fetchall()
    recovered = []
    for ticket_id, submitted_at in rows:
        if submitted_at:
            _block_unknown(conn, ticket_id)
        else:
            tickets.set_status(conn, ticket_id, "pending", reason=REASON_RECOVERED)
        _clear_session_link(conn, ticket_id)
        recovered.append(ticket_id)
    return recovered
