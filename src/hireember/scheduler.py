"""Daily schedule and the foreground loop that starts scheduled runs."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable

from hireember import runs, tickets

log = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 30
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


class ScheduleError(ValueError):
    """A schedule time is not a valid 24-hour HH:MM."""

    def __init__(self, value: str):
        super().__init__(f'Invalid time "{value}". Use 24-hour HH:MM, e.g. 08:00.')


@dataclass
class Schedule:
    times: list[str]
    apply: bool
    apply_limit: int


def parse_time(value: str) -> str:
    """Return zero-padded HH:MM for 00:00 to 23:59; raise ScheduleError otherwise."""
    m = _TIME.match(value or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ScheduleError(value)
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.astimezone()


def get_schedule(conn: sqlite3.Connection) -> Schedule:
    raw = tickets.get_setting(conn, "schedule_times", "") or ""
    try:
        limit = int(tickets.get_setting(conn, "schedule_apply_limit", str(runs.DEFAULT_APPLY_LIMIT)))
    except (TypeError, ValueError):
        limit = runs.DEFAULT_APPLY_LIMIT
    return Schedule(times=[t for t in raw.split(",") if t],
                    apply=tickets.get_setting(conn, "schedule_apply", "off") == "on",
                    apply_limit=limit)


def set_schedule(conn: sqlite3.Connection, times: list[str],
                 now: datetime | None = None) -> Schedule:
    """Replace the schedule; slots before ``now`` are not fired."""
    clean = sorted({parse_time(t) for t in times})
    tickets.set_setting(conn, "schedule_times", ",".join(clean))
    tickets.set_setting(conn, "schedule_last_slot", _aware(now or _local_now()).isoformat())
    return get_schedule(conn)


def clear_schedule(conn: sqlite3.Connection) -> None:
    tickets.set_setting(conn, "schedule_times", "")


def set_apply(conn: sqlite3.Connection, on: bool | None = None,
              limit: int | None = None) -> Schedule:
    if limit is not None and limit < 1:
        raise ValueError("The apply limit must be at least 1.")
    if on is not None:
        tickets.set_setting(conn, "schedule_apply", "on" if on else "off")
    if limit is not None:
        tickets.set_setting(conn, "schedule_apply_limit", str(limit))
    return get_schedule(conn)


def due_slot(conn: sqlite3.Connection, now: datetime) -> datetime | None:
    """The latest slot after the last one consumed and not after ``now``, or None."""
    schedule = get_schedule(conn)
    raw = tickets.get_setting(conn, "schedule_last_slot")
    if not schedule.times or not raw:
        return None
    now = _aware(now)
    try:
        last = _aware(datetime.fromisoformat(raw))
    except ValueError:
        return None
    best = None
    day = last.astimezone(now.tzinfo).date()
    while day <= now.date():
        for text in schedule.times:
            hh, mm = text.split(":")
            slot = datetime.combine(day, time(int(hh), int(mm)), tzinfo=now.tzinfo)
            if last < slot <= now and (best is None or slot > best):
                best = slot
        day = day.fromordinal(day.toordinal() + 1)
    return best


def _applied_today(conn: sqlite3.Connection, now: datetime) -> int:
    today = _aware(now).astimezone(timezone.utc).date().isoformat()
    return conn.execute("SELECT COUNT(*) FROM tickets WHERE submitted_at IS NOT NULL "
                        "AND date(submitted_at) = ?", (today,)).fetchone()[0]


def tick(conn: sqlite3.Connection | None = None, now: datetime | None = None, *,
         stages: runs.Stages | None = None) -> runs.RunSummary | None:
    """Start one scheduled run if a slot is due (several missed slots start exactly one)."""
    if conn is None:
        from hireember.database import get_connection

        conn = get_connection()
    now = _aware(now or _local_now())
    slot = due_slot(conn, now)
    if slot is None:
        return None
    tickets.set_setting(conn, "schedule_last_slot", slot.isoformat())
    schedule = get_schedule(conn)
    remaining = max(0, schedule.apply_limit - _applied_today(conn, now))
    try:
        return runs.execute_run("scheduled", stages=stages, apply=schedule.apply,
                                apply_limit=remaining, conn=conn, now=now)
    except runs.RunInProgressError as e:
        runs.log_event(conn, None, "scheduler", f"Skipped the {slot.strftime('%H:%M')} run: {e}",
                       level="info")
        return None


def serve(poll_seconds: float = DEFAULT_POLL_SECONDS, once: bool = False,
          stop: threading.Event | None = None, clock: Callable[[], datetime] | None = None,
          stages: runs.Stages | None = None) -> None:
    """Tick every ``poll_seconds`` until ``stop`` is set (or once)."""
    from hireember.database import get_connection

    stop = stop or threading.Event()
    clock = clock or _local_now
    conn = get_connection()
    while not stop.is_set():
        try:
            tick(conn, clock(), stages=stages)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("Scheduled run failed to start")
        if once:
            return
        stop.wait(poll_seconds)
