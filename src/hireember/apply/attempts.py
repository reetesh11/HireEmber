"""Attempt log: one row per step an apply run takes on a ticket."""

import sqlite3

from hireember import tickets


def start_attempt(conn: sqlite3.Connection, ticket_id: int) -> int:
    """Return the next attempt number for the ticket (1 for the first)."""
    row = conn.execute("SELECT MAX(attempt) FROM attempt_log WHERE ticket_id = ?",
                       (ticket_id,)).fetchone()
    return (row[0] or 0) + 1


def log_step(conn: sqlite3.Connection, ticket_id: int, attempt: int, kind: str,
             field: str = "", source: str = "", detail: str = "") -> None:
    """Append one step to the ticket's attempt log."""
    conn.execute(
        "INSERT INTO attempt_log (ticket_id, attempt, time, kind, field, source, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, attempt, tickets._now(), kind, field, source, detail),
    )
    conn.commit()


def get_log(conn: sqlite3.Connection, ticket_id: int) -> list[dict]:
    """Return the ticket's log rows, oldest first."""
    rows = conn.execute(
        "SELECT id, attempt, time, kind, field, source, detail FROM attempt_log "
        "WHERE ticket_id = ? ORDER BY id", (ticket_id,)).fetchall()
    return [dict(zip(r.keys(), tuple(r))) for r in rows]
