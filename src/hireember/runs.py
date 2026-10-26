"""Runs: one summary row per run, a single-run lock shared by every trigger, single stages."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from hireember import tickets

LOCK_MAX_AGE = timedelta(hours=24)
DEFAULT_APPLY_LIMIT = 25
STAGE_NAMES = ("discover", "score", "tailor", "apply")
KIND_RUN_BLOCKED = "run blocked"
DEFAULT_REASON = "Needs your attention"


class RunInProgressError(Exception):
    """Another run, stage or apply is already holding the run lock."""

    def __init__(self) -> None:
        super().__init__("A run is already in progress.")


@dataclass
class Stages:
    """The stage callables a run drives; injected so tests can fake them."""

    discover: Callable[..., dict]
    enrich: Callable[..., dict]
    score: Callable[..., dict]
    tailor: Callable[..., dict]
    apply: Callable[..., dict]


@dataclass
class RunSummary:
    id: int
    kind: str
    trigger: str
    status: str
    started_at: str
    ended_at: str | None
    found: int
    scored: int
    skipped: int
    tickets_created: int
    tickets_blocked: int


@dataclass
class StageResult:
    stage: str
    message: str
    counts: dict


def _conn(conn: sqlite3.Connection | None) -> sqlite3.Connection:
    if conn is not None:
        return conn
    from hireember.database import get_connection

    return get_connection()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -- lock ---------------------------------------------------------------------

def is_pid_alive(pid: int) -> bool:
    """True when a process with this id exists."""
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_is_stale(row: sqlite3.Row | tuple) -> bool:
    pid, acquired_at = row[0], row[1]
    if not is_pid_alive(pid or 0):
        return True
    try:
        acquired = datetime.fromisoformat(acquired_at)
    except (TypeError, ValueError):
        return True
    if acquired.tzinfo is None:
        acquired = acquired.replace(tzinfo=timezone.utc)
    return _utcnow() - acquired > LOCK_MAX_AGE


def _reclaim_stale(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT pid, acquired_at, token FROM run_lock WHERE id = 1").fetchone()
    if row is None:
        return True
    if not _lock_is_stale(row):
        return False
    deleted = conn.execute("DELETE FROM run_lock WHERE id = 1 AND token = ?", (row[2],)).rowcount
    if deleted:
        conn.execute("UPDATE runs SET status = 'interrupted', ended_at = ? WHERE status = 'running'",
                     (_utcnow().isoformat(),))
    conn.commit()
    return True


def acquire_lock(conn: sqlite3.Connection) -> str:
    """Take the single-run lock and return its token; raise RunInProgressError when held."""
    token = uuid.uuid4().hex
    for _ in range(3):
        try:
            conn.execute("INSERT INTO run_lock (id, pid, token, acquired_at) VALUES (1, ?, ?, ?)",
                         (os.getpid(), token, _utcnow().isoformat()))
            conn.commit()
            return token
        except sqlite3.IntegrityError:
            conn.rollback()
            if not _reclaim_stale(conn):
                break
    raise RunInProgressError()


def release_lock(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM run_lock WHERE token = ?", (token,))
    conn.commit()


def is_running(conn: sqlite3.Connection) -> bool:
    """True when a live run holds the lock."""
    row = conn.execute("SELECT pid, acquired_at FROM run_lock WHERE id = 1").fetchone()
    return row is not None and not _lock_is_stale(row)


# -- log and rows -------------------------------------------------------------

def log_event(conn: sqlite3.Connection, run_id: int | None, source: str, message: str,
              level: str = "error") -> None:
    conn.execute("INSERT INTO run_log (run_id, time, source, level, message) VALUES (?, ?, ?, ?, ?)",
                 (run_id, _utcnow().isoformat(), source, level, message))
    conn.commit()


def get_run_log(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute("SELECT time, source, level, message FROM run_log WHERE run_id = ? "
                        "ORDER BY id", (run_id,)).fetchall()
    return [{"time": r[0], "source": r[1], "level": r[2], "message": r[3]} for r in rows]


_RUN_SELECT = ('SELECT id, kind, "trigger", status, started_at, ended_at, found, scored, skipped, '
               "tickets_created, tickets_blocked FROM runs")


def _summary(r) -> RunSummary:
    return RunSummary(
        id=r[0], kind=r[1] or "", trigger=r[2] or "", status=r[3] or "", started_at=r[4] or "",
        ended_at=r[5], found=r[6] or 0, scored=r[7] or 0, skipped=r[8] or 0,
        tickets_created=r[9] or 0, tickets_blocked=r[10] or 0)


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[RunSummary]:
    return [_summary(r) for r in conn.execute(f"{_RUN_SELECT} ORDER BY id DESC LIMIT ?", (limit,))]


def get_run(conn: sqlite3.Connection, run_id: int) -> RunSummary | None:
    row = conn.execute(f"{_RUN_SELECT} WHERE id = ?", (run_id,)).fetchone()
    return _summary(row) if row else None


def enqueue_blocked(conn: sqlite3.Connection) -> int:
    """Queue every blocked ticket that has no open queue item; return how many were added."""
    rows = conn.execute(
        "SELECT t.id, t.status_reason, j.application_url, j.url FROM tickets t "
        "LEFT JOIN jobs j ON j.url = t.job_url WHERE t.status = 'blocked for human' "
        "AND NOT EXISTS (SELECT 1 FROM queue_items q WHERE q.ticket_id = t.id "
        "AND q.resolved_at IS NULL) ORDER BY t.id").fetchall()
    for r in rows:
        conn.execute(
            "INSERT INTO queue_items (ticket_id, kind, reason, page_link, question_text) "
            "VALUES (?, ?, ?, ?, '')",
            (r[0], KIND_RUN_BLOCKED, (r[1] or "").strip() or DEFAULT_REASON, r[2] or r[3] or ""))
    conn.commit()
    return len(rows)


# -- runs ---------------------------------------------------------------------

def _count(result: dict | None, key: str) -> int:
    try:
        return int((result or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


def execute_run(trigger: str = "manual", *, stages: Stages | None = None, apply: bool = False,
                apply_limit: int | None = None, conn: sqlite3.Connection | None = None,
                now: datetime | None = None) -> RunSummary:
    """Run discover, enrich, score and tailor (and apply when asked) and write one runs row."""
    conn = _conn(conn)
    token = acquire_lock(conn)
    run_id: int | None = None
    status = "interrupted"
    counts = {"found": 0, "scored": 0, "skipped": 0, "created": 0, "blocked": 0}
    try:
        if stages is None:
            from hireember.stages import default_stages

            stages = default_stages()
        started = (now or _utcnow()).isoformat()
        cur = conn.execute('INSERT INTO runs (kind, "trigger", status, started_at) '
                           "VALUES ('full', ?, 'running', ?)", (trigger, started))
        run_id = cur.lastrowid
        conn.execute("UPDATE run_lock SET run_id = ? WHERE token = ?", (run_id, token))
        conn.commit()
        failed = False

        def call(name: str, fn: Callable[..., dict], *args) -> dict:
            nonlocal failed
            try:
                return fn(conn, run_id, *args) or {}
            except Exception as e:  # noqa: BLE001 - a failing stage must not stop the run
                failed = True
                log_event(conn, run_id, name, str(e) or type(e).__name__)
                return {}

        counts["found"] = _count(call("discover", stages.discover), "found")
        call("enrich", stages.enrich)
        scored = call("score", stages.score)
        counts["scored"], counts["skipped"] = _count(scored, "scored"), _count(scored, "skipped")
        call("tailor", stages.tailor)
        limit = DEFAULT_APPLY_LIMIT if apply_limit is None else apply_limit
        if apply and limit > 0:
            call("apply", stages.apply, limit)
        created = conn.execute("SELECT COUNT(*) FROM tickets WHERE created_at >= ?",
                               (started,)).fetchone()[0]
        blocked = enqueue_blocked(conn)
        status = "partial" if failed else "completed"
        counts["created"], counts["blocked"] = created, blocked
    finally:
        if run_id is not None:
            conn.execute(
                "UPDATE runs SET ended_at = ?, status = ?, found = ?, scored = ?, skipped = ?, "
                "tickets_created = ?, tickets_blocked = ?, summary = ? WHERE id = ?",
                (_utcnow().isoformat(), status, counts["found"], counts["scored"],
                 counts["skipped"], counts["created"], counts["blocked"],
                 f"found {counts['found']}, scored {counts['scored']}", run_id))
            conn.commit()
        release_lock(conn, token)
    return get_run(conn, run_id)  # type: ignore[arg-type]


# -- single stages --------------------------------------------------------------

def _stage_result(stage: str, result: dict) -> StageResult:
    n = lambda key: _count(result, key)  # noqa: E731
    messages = {
        "discover": f"discover: {n('found')} roles found, {n('new')} new.",
        "score": f"score: {n('scored')} scored, {n('skipped')} skipped.",
        "tailor": f"tailor: {n('created')} tickets created, {n('blocked')} blocked.",
        "apply": f"apply: {n('submitted')} submitted.",
    }
    return StageResult(stage, messages[stage], dict(result or {}))


def _store_result(conn: sqlite3.Connection, result: StageResult) -> None:
    tickets.set_setting(conn, "last_stage_result", json.dumps(
        {"stage": result.stage, "message": result.message, "counts": result.counts}))


def last_stage_result(conn: sqlite3.Connection) -> dict | None:
    raw = tickets.get_setting(conn, "last_stage_result")
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _check_stage(stage: str) -> None:
    if stage not in STAGE_NAMES:
        raise ValueError(f"Unknown stage {stage!r}. Valid stages: {', '.join(STAGE_NAMES)}.")


def _run_locked_stage(stage: str, stages: Stages | None, conn: sqlite3.Connection,
                      limit: int | None, min_score: int | None,
                      validation_mode: str) -> StageResult:
    if stages is None:
        from hireember.stages import default_stages

        stages = default_stages(min_score=min_score, validation_mode=validation_mode)
    fn = getattr(stages, stage)
    result = fn(conn, None, limit or 1) if stage == "apply" else fn(conn, None)
    if stage != "discover":
        enqueue_blocked(conn)
    stage_result = _stage_result(stage, result or {})
    _store_result(conn, stage_result)
    return stage_result


def run_stage(stage: str, *, stages: Stages | None = None, conn: sqlite3.Connection | None = None,
              limit: int | None = None, min_score: int | None = None,
              validation_mode: str = "normal") -> StageResult:
    """Run one stage under the run lock; no runs row is written."""
    _check_stage(stage)
    conn = _conn(conn)
    token = acquire_lock(conn)
    try:
        return _run_locked_stage(stage, stages, conn, limit, min_score, validation_mode)
    finally:
        release_lock(conn, token)


def start_stage_async(stage: str, *, stages: Stages | None = None, limit: int | None = None,
                      min_score: int | None = None,
                      conn: sqlite3.Connection | None = None) -> threading.Thread:
    """Take the lock now, then run the stage in a daemon thread that releases it."""
    _check_stage(stage)
    conn = _conn(conn)
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    token = acquire_lock(conn)

    def work() -> None:
        from hireember.database import get_connection

        own = get_connection(db_file) if db_file else conn
        try:
            _run_locked_stage(stage, stages, own, limit, min_score, "normal")
        except Exception as e:  # noqa: BLE001 - reported through the stored result
            log_event(own, None, stage, str(e) or type(e).__name__)
            _store_result(own, StageResult(stage, f"{stage}: failed. {e}", {}))
        finally:
            release_lock(own, token)

    thread = threading.Thread(target=work, name=f"stage-{stage}", daemon=True)
    thread.start()
    return thread
