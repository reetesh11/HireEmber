"""Application limits: open tickets per company, one-day company wait, applications per day.

Everything is computed from the database (``tickets.submitted_at``), so the limits hold
across batches, workers and restarts. The clock is only read through the ``now`` argument.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from hireember import tickets

DEFAULT_MAX_OPEN_PER_COMPANY = 3
DEFAULT_MAX_PER_DAY = 25
DEFAULT_COMPANY_WAIT_HOURS = 24

_OPEN_STATUSES = ("started", "applying", "blocked for human")
_FROM = ("FROM tickets t JOIN jobs j ON j.url = t.job_url "
         "LEFT JOIN companies c ON c.id = j.company_id")


@dataclass
class LimitResult:
    ok: bool
    reason: str = ""
    not_before: str | None = None


def _now(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int_setting(conn: sqlite3.Connection, key: str, default: int) -> int:
    try:
        return int(str(tickets.get_setting(conn, key, str(default))).strip())
    except ValueError:
        return default


def _company(conn: sqlite3.Connection, ticket_id: int) -> str:
    row = conn.execute(f"SELECT {tickets._COMPANY} {_FROM} WHERE t.id = ?", (ticket_id,)).fetchone()
    return row[0] if row else ""


def _wait_hours(conn: sqlite3.Connection) -> int:
    return _int_setting(conn, "company_wait_hours", DEFAULT_COMPANY_WAIT_HOURS)


def check_limits(conn: sqlite3.Connection, ticket_id: int, now: datetime | None = None) -> LimitResult:
    """Return whether the ticket may be applied to now; the first failing limit wins."""
    when = _now(now)
    company = _company(conn, ticket_id)
    if company:
        marks = ",".join("?" * len(_OPEN_STATUSES))
        open_count = conn.execute(
            f"SELECT COUNT(*) {_FROM} WHERE t.id != ? AND {tickets._COMPANY} = ? "
            f"AND t.status IN ({marks})", (ticket_id, company, *_OPEN_STATUSES)).fetchone()[0]
        if open_count >= _int_setting(conn, "max_open_per_company", DEFAULT_MAX_OPEN_PER_COMPANY):
            return LimitResult(False, f"limit: company ({open_count} open)", None)

        wait = timedelta(hours=_wait_hours(conn))
        rows = conn.execute(
            f"SELECT t.submitted_at {_FROM} WHERE t.id != ? AND {tickets._COMPANY} = ? "
            "AND t.submitted_at IS NOT NULL", (ticket_id, company)).fetchall()
        recent = [d for d in (_parse(r[0]) for r in rows) if d is not None and d + wait > when]
        if recent:
            until = max(recent) + wait
            return LimitResult(
                False, f"limit: company wait until {until.strftime('%Y-%m-%d %H:%M')}",
                until.isoformat())

    day = when.strftime("%Y-%m-%d")
    today = conn.execute("SELECT COUNT(*) FROM tickets WHERE submitted_at LIKE ?",
                         (day + "%",)).fetchone()[0]
    if today >= _int_setting(conn, "max_per_day", DEFAULT_MAX_PER_DAY):
        midnight = datetime(when.year, when.month, when.day, tzinfo=timezone.utc) + timedelta(days=1)
        return LimitResult(False, "limit: daily", midnight.isoformat())
    return LimitResult(True)


def hold_ticket(conn: sqlite3.Connection, ticket_id: int, result: LimitResult) -> None:
    """Keep the ticket pending with the limit reason and the time it becomes eligible."""
    if tickets.get_ticket(conn, ticket_id)["status"] != "pending":
        tickets.set_status(conn, ticket_id, "pending", reason=result.reason)
    tickets.set_reason(conn, ticket_id, result.reason, not_before=result.not_before)


def record_submission(conn: sqlite3.Connection, ticket_id: int, now: datetime | None = None) -> None:
    """Queue the company's other pending tickets behind the wait after a submission."""
    company = _company(conn, ticket_id)
    if not company:
        return
    until = _now(now) + timedelta(hours=_wait_hours(conn))
    reason = f"limit: company wait until {until.strftime('%Y-%m-%d %H:%M')}"
    rows = conn.execute(
        f"SELECT t.id {_FROM} WHERE t.id != ? AND t.status = 'pending' AND {tickets._COMPANY} = ?",
        (ticket_id, company)).fetchall()
    for (other,) in rows:
        tickets.set_reason(conn, other, reason, not_before=until.isoformat())


def eligible_ticket_ids(conn: sqlite3.Connection, now: datetime | None = None) -> list[int]:
    """Pending ticket ids whose not-before time has come, best score first."""
    when = _now(now)
    rows = conn.execute(
        "SELECT id, not_before FROM tickets WHERE status = 'pending' "
        "ORDER BY COALESCE(score, 0) DESC, id").fetchall()
    result = []
    for ticket_id, not_before in rows:
        due = _parse(not_before)
        if due is None or due <= when:
            result.append(ticket_id)
    return result
