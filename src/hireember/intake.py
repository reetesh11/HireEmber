"""Filter discovered jobs by title and location before they enter the pipeline.

A dropped job is still stored (so its URL is a duplicate next time and is never fetched again),
marked as not needing enrichment, and given a ``skipped`` ticket whose reason starts with
``title:`` or ``location:``. A job already stored is never re-filtered, so restoring one sticks.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from hireember import config, runs, search_config, tickets
from hireember.database import store_jobs
from hireember.location import location_skip_reason
from hireember.titles import title_filter

_MAX_LOGGED = 20


class DropTally:
    """Counts and titles of the jobs a discovery run dropped."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {"title": 0, "location": 0}
        self.items: list[tuple[str, str]] = []

    def add(self, title: str | None, reason: str) -> None:
        kind = reason.split(":", 1)[0]
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self.items.append((title or "", reason))

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def summary_line(self) -> str:
        return f"Dropped {self.total}: {self.counts['title']} title, {self.counts['location']} location"

    def hint(self, kept: int = 1) -> str:
        if not self.total:
            return ""
        text = f"{self.summary_line()}. Review them in Tickets (skipped) or edit rules in Profile."
        if kept == 0:
            text += " Check your target roles and locations in Profile."
        return text


class JobFilter:
    """Title filter first, then the location check, with the lists read once."""

    def __init__(self, search_cfg: dict, profile: dict) -> None:
        self.cfg = search_cfg
        self.profile = profile
        self.include, self.exclude = search_config.title_lists(search_cfg)

    @classmethod
    def load(cls, search_cfg: dict | None = None, profile: dict | None = None) -> JobFilter:
        if search_cfg is None:
            search_cfg = search_config.load()
        if profile is None:
            try:
                profile = config.load_profile()
            except (OSError, ValueError):
                profile = {}
        return cls(search_cfg, profile if isinstance(profile, dict) else {})

    def reason(self, title: str | None, location: str | None) -> str | None:
        return (title_filter(title, self.include, self.exclude)
                or location_skip_reason(location, self.profile, self.cfg))


def mark_dropped(conn: sqlite3.Connection, url: str, reason: str, title: str | None,
                 tally: DropTally | None = None) -> None:
    """Mark a stored job as dropped: no enrichment, a ``skipped`` ticket with the reason."""
    conn.execute("UPDATE jobs SET detail_scraped_at = ? WHERE url = ? AND detail_scraped_at IS NULL",
                 (datetime.now(timezone.utc).isoformat(), url))
    conn.commit()
    tickets.open_ticket(conn, url, "skipped", reason)
    if tally is not None:
        tally.add(title, reason)


def store_filtered(conn: sqlite3.Connection, jobs: list[dict], *, site: str, strategy: str,
                   flt: JobFilter | None = None, tally: DropTally | None = None,
                   now: str | None = None) -> tuple[int, int, int]:
    """Store jobs, dropping those the filter rejects; return (new_kept, existing, dropped)."""
    flt = flt or JobFilter.load()
    new_kept = existing = dropped = 0
    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        known = conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone() is not None
        reason = None if known else flt.reason(job.get("title"), job.get("location"))
        new, dup = store_jobs(conn, [job], site=site, strategy=strategy, now=now)
        existing += dup
        if not new:
            continue
        if reason:
            mark_dropped(conn, url, reason, job.get("title"), tally)
            dropped += 1
        else:
            new_kept += 1
    return new_kept, existing, dropped


def write_run_log(conn: sqlite3.Connection, run_id: int | None, tally: DropTally) -> None:
    """Write the drop summary and up to 20 dropped titles to the run log."""
    if not tally.total or run_id is None:
        return
    runs.log_event(conn, run_id, "discover", tally.summary_line(), level="info")
    for title, reason in tally.items[:_MAX_LOGGED]:
        runs.log_event(conn, run_id, "discover", f"dropped: {title} ({reason})", level="info")
    if len(tally.items) > _MAX_LOGGED:
        runs.log_event(conn, run_id, "discover", f"...and {len(tally.items) - _MAX_LOGGED} more",
                       level="info")
