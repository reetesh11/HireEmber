"""Add jobs by URL: fetch and read a job page, store it as a manual job and open its ticket."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from hireember import gating, runs, tickets
from hireember.config import is_linkedin_url
from hireember.database import store_jobs
from hireember.enrichment.page import extract_with_ai, looks_like_login, parse_job_page
from hireember.urlfetch import INVALID_REASON, SCHEME_REASON, FetchError, check_url, fetch_page

log = logging.getLogger(__name__)

TRACKING_PARAMS = ("gh_src", "source")  # plus any name starting with "utm_"

LINKEDIN_REASON = "LinkedIn links are not supported because they need a signed-in session."
LOGIN_REASON = "The page needs you to sign in, so the description could not be read."
NO_DESCRIPTION_REASON = "No job description was found on the page."
UNEXPECTED_REASON = "Something went wrong adding this link."
ADDED_REASON = "added by link"
DUPLICATE_REASON = "already added"


def _is_tracking(name: str) -> bool:
    low = name.lower()
    return low.startswith("utm_") or low in TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Drop tracking parameters and the fragment, lower-case the host and strip a trailing slash."""
    text = (url or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                       if not _is_tracking(k)])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


@dataclass
class AddResult:
    status: str  # "added", "duplicate" or "failed"
    job_url: str
    ticket_id: int | None
    reason: str = ""


def _no_dns(*args, **kwargs):
    raise OSError("name resolution is left to the fetch")


def _precheck(url: str) -> str | None:
    """The refusal reason for a URL that needs no network to judge, or None."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return INVALID_REASON
    scheme = parts.scheme.lower()
    if scheme and scheme not in ("http", "https"):
        return SCHEME_REASON
    if not scheme or not host:
        return INVALID_REASON
    if is_linkedin_url(url):
        return LINKEDIN_REASON
    return None


def _find_existing(conn: sqlite3.Connection, url: str) -> dict | None:
    """The stored job whose url or application_url matches ``url`` after normalisation."""
    host = (urlsplit(url).hostname or "").lower()
    rows = conn.execute(
        "SELECT url, application_url, full_description FROM jobs WHERE lower(url) LIKE ? "
        "OR lower(application_url) LIKE ?", (f"%{host}%", f"%{host}%")).fetchall()
    for row in rows:
        if url in (normalize_url(row[0]), normalize_url(row[1] or "")):
            return {"url": row[0], "full_description": row[2]}
    return None


def _fail(conn: sqlite3.Connection, url: str, reason: str, *, store: bool) -> AddResult:
    if not store:
        return AddResult("failed", url, None, reason)
    now = tickets._now()
    store_jobs(conn, [{"url": url, "title": url}], urlsplit(url).hostname or "", "manual")
    conn.execute("UPDATE jobs SET detail_scraped_at = COALESCE(detail_scraped_at, ?) WHERE url = ?", (now, url))
    conn.commit()
    ticket_id = tickets.open_ticket(conn, url, "blocked for human", reason)
    runs.enqueue_blocked(conn)
    return AddResult("failed", url, ticket_id, reason)


def _resolve_queue(conn: sqlite3.Connection, ticket_id: int) -> None:
    conn.execute("UPDATE queue_items SET resolved_at = ? WHERE ticket_id = ? AND resolved_at IS NULL",
                 (tickets._now(), ticket_id))
    conn.commit()


def _from_text(text: str) -> dict:
    cleaned = text.strip()
    first = cleaned.splitlines()[0].strip() if cleaned else ""
    return {"title": first, "company": "", "location": "", "description": cleaned, "application_url": ""}


def _add(conn: sqlite3.Connection, url: str, fetch, extract, text: str | None) -> AddResult:
    refusal = _precheck(url)
    if refusal:
        return _fail(conn, url, refusal, store=False)

    existing = _find_existing(conn, url)
    job_url = url
    if existing:
        ticket = tickets.get_ticket_by_url(conn, existing["url"])
        reopen = (text is not None and ticket is not None and ticket["status"] == "blocked for human"
                  and not existing["full_description"])
        if ticket is not None and not reopen:
            return AddResult("duplicate", url, ticket["id"], DUPLICATE_REASON)
        job_url = existing["url"]

    if text is not None:
        data = _from_text(text)
    else:
        refusal = check_url(url, resolver=_no_dns)
        if refusal:
            return _fail(conn, job_url, refusal, store=True)
        try:
            page = fetch(url)
        except FetchError as e:
            return _fail(conn, job_url, e.reason, store=True)
        if looks_like_login(page.html, page.url):
            return _fail(conn, job_url, LOGIN_REASON, store=True)
        data = parse_job_page(page.html, page.url, extract=extract)
        if data is None:
            return _fail(conn, job_url, NO_DESCRIPTION_REASON, store=True)

    host = urlsplit(url).hostname or ""
    store_jobs(conn, [{"url": job_url, "title": data["title"], "location": data["location"],
                       "company": data["company"]}], host, "manual")
    conn.execute(
        "UPDATE jobs SET title = COALESCE(NULLIF(?, ''), title), location = COALESCE(NULLIF(?, ''), location), "
        "strategy = 'manual', full_description = ?, application_url = COALESCE(NULLIF(?, ''), application_url), "
        "detail_scraped_at = ? WHERE url = ?",
        (data["title"], data["location"], data["description"], data["application_url"], tickets._now(), job_url))
    if data["company"]:
        tickets.set_job_company(conn, job_url, data["company"])
    conn.commit()

    ticket = tickets.get_ticket_by_url(conn, job_url)
    if ticket is None:
        ticket_id = tickets.open_ticket(conn, job_url, "pending", ADDED_REASON)
    else:
        ticket_id = ticket["id"]
        if ticket["status"] == "blocked for human":
            tickets.set_status(conn, ticket_id, "pending", reason=ADDED_REASON)
        _resolve_queue(conn, ticket_id)
    return AddResult("added", job_url, ticket_id, "")


def add_job_from_url(conn: sqlite3.Connection, url: str, *, fetch=None, extract=None,
                     text: str | None = None) -> AddResult:
    """Fetch and read one job page, store it as a manual job and open its ticket.

    ``fetch(url)`` and ``extract(url, text)`` default to the real fetcher and AI extractor, looked up at call time.
    """
    norm = normalize_url(url)
    fetch = fetch or fetch_page
    extract = extract or extract_with_ai
    try:
        return _add(conn, norm, fetch, extract, text)
    except Exception as e:  # noqa: BLE001 - one bad link must not stop the others
        log.error("Adding a job link failed: %s", type(e).__name__)
        log.debug("Adding %s failed", norm, exc_info=True)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        return AddResult("failed", norm, None, UNEXPECTED_REASON)


# -- running several links ----------------------------------------------------

STOPPED_NO_APPLY = "Stopped at ticket (run with --apply to apply)"
ALREADY_IN_TICKETS = "Already in your tickets"
DAILY_LIMIT_STEP = "Daily apply limit reached; will wait."
WAITING_AT_REVIEW = "Waiting at review"
STATE_KEY = "add_jobs_state"

PLAIN_REASONS = {
    "captcha": "A CAPTCHA needs you to solve it.",
    "account needed": "A sign-in is needed to continue.",
}


@dataclass
class AddRow:
    url: str
    status: str  # "added", "already added" or "failed"
    ticket_id: int | None
    score: int | None
    reason: str
    next_step: str


def plain_reason(reason: str | None) -> str:
    text = (reason or "").strip()
    return PLAIN_REASONS.get(text, text)


def next_step(ticket: dict | None, *, applying: bool = False) -> str:
    """The plain-language next step for a ticket after an add (and apply) run."""
    if ticket is None:
        return ""
    status, reason = ticket["status"], ticket["status_reason"] or ""
    if status == "applied":
        return "Applied"
    if status == "blocked for human":
        return f"Blocked for human: {plain_reason(reason)}"
    if "limit: daily" in reason:
        return DAILY_LIMIT_STEP
    return WAITING_AT_REVIEW if applying else STOPPED_NO_APPLY


def _ticket_of(conn: sqlite3.Connection, ticket_id: int | None) -> dict | None:
    return tickets.get_ticket(conn, ticket_id) if ticket_id is not None else None


def _row_for(conn: sqlite3.Connection, url: str, result: AddResult) -> AddRow:
    if result.status == "duplicate":
        ticket = _ticket_of(conn, result.ticket_id)
        return AddRow(url, "already added", result.ticket_id, ticket["score"] if ticket else None,
                      result.reason, ALREADY_IN_TICKETS)
    if result.status == "failed":
        step = f"Blocked for human: {result.reason}" if result.ticket_id is not None else result.reason
        return AddRow(url, "failed", result.ticket_id, None, result.reason, step)
    # Added: score the job, then tailor it when the ticket is pending.
    scored = gating.score_job_for_ticket(conn, result.job_url)
    if scored.status == "pending":
        gating.tailor_ticket(conn, scored.ticket_id)
    ticket = tickets.get_ticket(conn, result.ticket_id)
    return AddRow(url, "added", result.ticket_id, ticket["score"], "", next_step(ticket))


def _add_one(conn: sqlite3.Connection, url: str, *, text: str | None, fetch, extract) -> AddRow:
    try:
        result = add_job_from_url(conn, url, fetch=fetch, extract=extract, text=text)
        return _row_for(conn, url, result)
    except Exception as e:  # noqa: BLE001 - a failure on one link never stops the others
        log.error("Processing a job link failed: %s", type(e).__name__)
        log.debug("Processing %s failed", url, exc_info=True)
        return AddRow(url, "failed", None, None, UNEXPECTED_REASON, UNEXPECTED_REASON)


def run_add_jobs(conn: sqlite3.Connection, urls: list[str], *, apply: bool = False, review: bool = True,
                 text: str | None = None, fetch=None, extract=None, progress=None,
                 now=None) -> list[AddRow]:
    """Add each URL, score and tailor the new jobs and, with ``apply``, apply to exactly those jobs.

    One row is returned per input URL, in input order.
    """
    rows: list[AddRow] = []
    for done, url in enumerate(urls, start=1):
        rows.append(_add_one(conn, url, text=text, fetch=fetch, extract=extract))
        log.info("Job link %d of %d: %s", done, len(urls), rows[-1].status)
        if progress:
            progress(done, len(urls))
    if apply:
        apply_added(conn, rows, review=review, now=now)
    return rows


def format_summary(rows: list[AddRow]) -> str:
    added = sum(r.status == "added" for r in rows)
    already = sum(r.status == "already added" for r in rows)
    failed = sum(r.status == "failed" for r in rows)
    return f"{len(rows)} URLs: {added} added, {already} already added, {failed} failed."


def save_state(conn: sqlite3.Connection, *, running: bool, rows: list[AddRow],
               progress: dict | None) -> None:
    tickets.set_setting(conn, STATE_KEY, json.dumps(
        {"running": running, "results": [asdict(r) for r in rows], "progress": progress}))


def load_state(conn: sqlite3.Connection) -> dict:
    raw = tickets.get_setting(conn, STATE_KEY)
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {"results": list(data.get("results") or []), "progress": data.get("progress")}


def _preflight_problem(outcome) -> str:
    titles = [n.title for n in getattr(outcome, "missing", None) or []]
    return ", ".join(titles) if titles else "setup is incomplete"


def apply_added(conn: sqlite3.Connection, rows: list[AddRow], *, review: bool, now=None) -> None:
    """Apply to the jobs added in this run, one launcher call each, and update their rows in place.

    ``review`` is always passed to the launcher as an explicit bool, so the saved setting is never used.
    """
    from hireember import preflight, scheduler
    from hireember.apply import launcher

    todo = [r for r in rows if r.status == "added"
            and (tickets.get_ticket(conn, r.ticket_id)["status"] == "pending")]
    if not todo:
        return
    outcome = preflight.run_preflight("apply", [], no_prompt=True)
    if not outcome.proceed:
        problem = _preflight_problem(outcome)
        for r in todo:
            r.next_step = f"Stopped at ticket: {problem}"
        return
    moment = now or datetime.now(timezone.utc)
    remaining = max(0, scheduler.get_schedule(conn).apply_limit - scheduler._applied_today(conn, moment))
    for r in todo[remaining:]:
        r.next_step = DAILY_LIMIT_STEP
    for r in todo[:remaining]:
        job_url = conn.execute("SELECT job_url FROM tickets WHERE id = ?", (r.ticket_id,)).fetchone()[0]
        try:
            launcher.main(limit=1, target_url=job_url, headless=False, review=bool(review))
        except Exception as e:  # noqa: BLE001 - one failed apply never stops the others
            log.error("Applying to a job link failed: %s", type(e).__name__)
            log.debug("Applying to %s failed", job_url, exc_info=True)
        r.next_step = next_step(tickets.get_ticket(conn, r.ticket_id), applying=True)
        r.score = tickets.get_ticket(conn, r.ticket_id)["score"]
