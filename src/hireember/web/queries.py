"""Read-side queries for the web dashboard: tickets, links, blocked queue and CSV export."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from hireember import logs, usage
from hireember.tickets import ALLOWED_STATUSES

NO_LINK = "No link available"
SORT_COLUMNS = ("company", "title", "location", "status", "score", "resume", "applied", "updated")
CSV_HEADER = ("company", "title", "location", "status", "score", "resume used", "applied date",
              "links", "notes")
_NEEDS_ATTENTION = "Needs your attention"
_SCORE_ERROR = "Enter a whole number from 0 to 100."
_ORDER_ERROR = "From date must be on or before To date."
_REVIEW_YOURSELF = "Review and complete this step yourself"


class FilterError(ValueError):
    """A ticket filter value is invalid."""


@dataclass
class TicketFilters:
    company: str = ""
    score_min: int | None = None
    score_max: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    resume_id: int | None = None


# -- links and next steps ---------------------------------------------------

def _is_local(value: str) -> bool:
    return not re.match(r"https?://", value.strip(), re.IGNORECASE)


def status_link(ticket: dict) -> dict | None:
    """The one link that matters for the ticket's status, or None when nothing is stored."""
    status = ticket.get("status")
    if status == "started":
        label, value = "Tailored files", ticket.get("tailored_resume_path")
    elif status == "applying":
        label, value = "Live browser session", ticket.get("session_link")
    elif status == "blocked for human":
        label = "Page needing action"
        value = ticket.get("queue_page_link") or ticket.get("resume_link")
    elif status == "applied":
        label, value = "Confirmation", ticket.get("confirmation_link")
    else:
        label, value = "Job posting", ticket.get("job_url")
    value = (value or "").strip()
    if not value:
        return None
    return {"label": label, "url": value, "local": _is_local(value)}


def next_step(kind: str | None) -> str:
    """What the user should do next for a blocked ticket of the given reason."""
    k = (kind or "").lower()
    if k == "account needed":
        return "Create an account"
    if k == "captcha":
        return "Solve the CAPTCHA"
    if k in ("unknown question", "conflicting answers", "sensitive question"):
        return "Answer the question"
    if k in ("identity check", "video or biometric", "manual site", "manual ats"):
        return _REVIEW_YOURSELF
    if "sign in" in k or "login" in k:
        return "Sign in"
    return "Review"


# -- filters and listing ----------------------------------------------------

def _check_score(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise FilterError(_SCORE_ERROR)
    return value


def _check_date(value) -> str | None:
    if value is None or value == "":
        return None
    try:
        date.fromisoformat(str(value))
    except ValueError:
        raise FilterError("Enter a date as YYYY-MM-DD.") from None
    return str(value)


_COMPANY_EXPR = ("COALESCE(NULLIF(TRIM(CASE WHEN j.company_id IS NOT NULL "
                 "THEN c.name ELSE j.site END), ''), '')")
_APPLIED_EXPR = (
    "CASE WHEN t.status = 'applied' THEN COALESCE(NULLIF(substr(t.submitted_at, 1, 10), ''), "
    "(SELECT substr(MAX(e.time), 1, 10) FROM ticket_events e "
    "WHERE e.ticket_id = t.id AND e.status = 'applied')) END"
)
_SORT_SQL = {
    "company": f"LOWER({_COMPANY_EXPR})",
    "title": "LOWER(COALESCE(j.title, ''))",
    "location": "LOWER(COALESCE(j.location, ''))",
    "status": "t.status",
    "score": "t.score",
    "resume": "LOWER(r.name)",
    "applied": "applied_date",
    "updated": "t.updated_at",
}
_SELECT = f"""
SELECT t.id, {_COMPANY_EXPR} AS company, COALESCE(j.title, '') AS title,
  COALESCE(j.location, '') AS location, t.status, COALESCE(t.status_reason, '') AS status_reason,
  t.score, t.resume_id, r.name AS resume_name, {_APPLIED_EXPR} AS applied_date,
  t.created_at, t.updated_at, t.notes, t.referral_note, t.job_url,
  t.tailored_resume_path, t.session_link, t.confirmation_link, t.resume_link,
  CASE WHEN t.status = 'blocked for human' THEN (SELECT q.page_link FROM queue_items q
    WHERE q.ticket_id = t.id AND q.resolved_at IS NULL AND COALESCE(q.page_link, '') != ''
    ORDER BY q.id DESC LIMIT 1) END AS queue_page_link
FROM tickets t
LEFT JOIN jobs j ON j.url = t.job_url
LEFT JOIN companies c ON c.id = j.company_id
LEFT JOIN resumes r ON r.id = t.resume_id
"""
_INTERNAL = ("tailored_resume_path", "session_link", "confirmation_link", "resume_link",
             "queue_page_link")


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_tickets(conn: sqlite3.Connection, filters: TicketFilters | None = None,
                 sort: str = "updated", direction: str = "desc") -> list[dict]:
    """Tickets with job, company, resume and link, filtered and sorted in one query."""
    if sort not in _SORT_SQL:
        raise ValueError(f"Unknown sort {sort!r}. Allowed: {', '.join(SORT_COLUMNS)}.")
    if direction not in ("asc", "desc"):
        raise ValueError(f"Unknown direction {direction!r}. Allowed: asc, desc.")
    f = filters or TicketFilters()
    smin, smax = _check_score(f.score_min), _check_score(f.score_max)
    dfrom, dto = _check_date(f.date_from), _check_date(f.date_to)
    if dfrom and dto and dfrom > dto:
        raise FilterError(_ORDER_ERROR)
    where: list[str] = []
    params: list = []
    company = (f.company or "").strip()
    if company:
        where.append(f"LOWER({_COMPANY_EXPR}) LIKE ? ESCAPE '\\'")
        params.append(_like(company.lower()))
    if smin is not None:
        where.append("t.score >= ?")
        params.append(smin)
    if smax is not None:
        where.append("t.score <= ?")
        params.append(smax)
    day = f"COALESCE({_APPLIED_EXPR}, substr(t.created_at, 1, 10))"
    if dfrom:
        where.append(f"{day} >= ?")
        params.append(dfrom)
    if dto:
        where.append(f"{day} <= ?")
        params.append(dto)
    if f.resume_id is not None:
        where.append("t.resume_id = ?")
        params.append(f.resume_id)
    sql = _SELECT + (" WHERE " + " AND ".join(where) if where else "")
    key = _SORT_SQL[sort]
    sql += f" ORDER BY ({key} IS NULL), {key} {direction}, t.id {direction}"
    return [_ticket_row(r) for r in conn.execute(sql, params).fetchall()]


def _ticket_row(r: sqlite3.Row) -> dict:
    row = dict(zip(r.keys(), tuple(r)))
    row["link"] = status_link(row)
    for k in _INTERNAL:
        row.pop(k, None)
    return row


def get_ticket_row(conn: sqlite3.Connection, ticket_id: int) -> dict | None:
    """One ticket in the same shape as ``list_tickets`` rows, or None."""
    r = conn.execute(_SELECT + " WHERE t.id = ?", (ticket_id,)).fetchone()
    return _ticket_row(r) if r else None


def status_counts(tickets: list[dict]) -> dict[str, int]:
    counts = {s: 0 for s in ALLOWED_STATUSES}
    for t in tickets:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    return counts


# -- blocked queue ----------------------------------------------------------

def blocked_queue(conn: sqlite3.Connection, ticket_id: int | None = None) -> list[dict]:
    """Every ticket blocked for a human, with its reason, next step and open question."""
    sql = _SELECT + " WHERE t.status = 'blocked for human'"
    params: list = []
    if ticket_id is not None:
        sql += " AND t.id = ?"
        params.append(ticket_id)
    items = []
    for r in conn.execute(sql + " ORDER BY t.updated_at, t.id", params).fetchall():
        row = dict(zip(r.keys(), tuple(r)))
        q = conn.execute(
            "SELECT id, kind, reason, question_text FROM queue_items "
            "WHERE ticket_id = ? AND resolved_at IS NULL ORDER BY id DESC LIMIT 1",
            (row["id"],)).fetchone()
        kind = (q["kind"] if q and q["kind"] else None) or row["status_reason"]
        reason = (q["reason"] if q and q["reason"] else None) or row["status_reason"] \
            or _NEEDS_ATTENTION
        items.append({
            "ticket_id": row["id"], "company": row["company"], "title": row["title"],
            "reason": reason, "next_step": next_step(kind or reason), "link": status_link(row),
            "queue_item_id": q["id"] if q else None,
            "question": (q["question_text"] or None) if q else None, "kind": kind or None,
        })
    return items


# -- CSV --------------------------------------------------------------------

def _guard(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def tickets_csv(conn: sqlite3.Connection, filters: TicketFilters | None = None,
                sort: str = "updated", direction: str = "desc") -> str:
    """The current ticket view as RFC 4180 CSV text (no BOM)."""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for t in list_tickets(conn, filters, sort, direction):
        notes = t["notes"] or ""
        if t["referral_note"]:
            notes = (notes + "\n" if notes else "") + f"Referral: {t['referral_note']}"
        writer.writerow([_guard(v) for v in (
            t["company"], t["title"], t["location"], t["status"],
            "" if t["score"] is None else t["score"], t["resume_name"] or "",
            t["applied_date"] or "", t["link"]["url"] if t["link"] else "", notes)])
    return out.getvalue()


# -- runs page ----------------------------------------------------------------

_RUN_COLUMNS = (("Started", "started_at"), ("Trigger", "trigger"), ("Status", "status"),
                ("Found", "found"), ("Scored", "scored"), ("Skipped", "skipped"),
                ("Tickets created", "tickets_created"), ("Tickets blocked", "tickets_blocked"))


def run_log_link_html(run_id: int) -> str:
    """A link to the run's log file, or "Log removed" when the file is gone."""
    if logs.run_log_path(run_id).is_file():
        return f'<a href="/logs/runs/{int(run_id)}">Log</a>'
    return "Log removed"


def runs_html(conn: sqlite3.Connection, fragment: bool = False, limit: int = 50) -> str:
    """The runs summary as server-rendered HTML (every value escaped); a full page unless fragment."""
    from dataclasses import asdict
    from html import escape

    from hireember.runs import list_runs

    runs = [asdict(r) for r in list_runs(conn, limit)]
    if runs:
        head = "".join(f'<th scope="col">{escape(label)}</th>' for label, _ in _RUN_COLUMNS)
        head += '<th scope="col">Log</th>'
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(str(r[key]))}</td>" for _, key in _RUN_COLUMNS)
            + f"<td>{run_log_link_html(r['id'])}</td></tr>"
            for r in runs)
        body = f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    else:
        body = "<p>No runs yet.</p>"
    section = f'<section id="runs-summary"><h2>Runs</h2>{body}</section>'
    if fragment:
        return section
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>HireEmber runs</title>'
            f"</head><body>{section}</body></html>")


# -- ticket page extras ---------------------------------------------------------

USAGE_LABELS = (("scoring", "Scoring"), ("tailoring", "Tailoring"), ("applying", "Applying"))


def ticket_logs(conn: sqlite3.Connection, ticket_id: int) -> list[dict]:
    """Attempt logs for a ticket, newest first, with whether each file still exists."""
    rows = conn.execute("SELECT DISTINCT attempt FROM attempt_log WHERE ticket_id = ? "
                        "ORDER BY attempt DESC", (ticket_id,)).fetchall()
    return [{"attempt": r[0], "url": f"/logs/tickets/{ticket_id}/{r[0]}",
             "available": logs.attempt_log_path(ticket_id, r[0]).is_file()} for r in rows]


def ticket_usage(conn: sqlite3.Connection, ticket_id: int) -> dict:
    return usage.get_usage(conn, ticket_id)


def ticket_extras_html(conn: sqlite3.Connection, ticket_id: int, fragment: bool = False) -> str:
    """The ticket page's Logs and Model and tokens sections (every value escaped)."""
    from html import escape

    items = []
    for entry in ticket_logs(conn, ticket_id):
        n = entry["attempt"]
        if entry["available"]:
            items.append(f'<li><a href="{entry["url"]}">Attempt {n} log</a></li>')
        else:
            items.append(f"<li>Attempt {n}: Log removed</li>")
    logs_html = f"<ul>{''.join(items)}</ul>" if items else "<p>No attempt log yet.</p>"
    usage = ticket_usage(conn, ticket_id)
    rows = []
    for key, label in USAGE_LABELS:
        u = usage.get(key)
        if u is None:
            cells = ["-"] * 4
        else:
            cells = [u["model"], f"{u['input_tokens']:,}", f"{u['output_tokens']:,}",
                     f"{u['total_tokens']:,}"]
        rows.append("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in [label, *cells]) + "</tr>")
    head = "".join(f'<th scope="col">{h}</th>' for h in
                   ("Stage", "Model", "Input tokens", "Output tokens", "Total tokens"))
    section = ('<section id="ticket-extras"><h2>Logs</h2>' + logs_html
               + "<h2>Model and tokens</h2>"
               + f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
               + "</section>")
    if fragment:
        return section
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f"<title>HireEmber ticket {ticket_id}</title></head><body>{section}</body></html>")
