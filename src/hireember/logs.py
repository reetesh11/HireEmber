"""Log files for runs and ticket attempts, kept under the data folder's logs directory."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hireember import config

RETENTION_DAYS = 90
_SECRET_SUFFIXES = ("KEY", "TOKEN", "SECRET")
_warned = False


def log_root() -> Path:
    return Path(config.LOG_DIR)


def run_log_path(run_id: int) -> Path:
    return log_root() / "runs" / f"run-{int(run_id)}.log"


def attempt_log_path(ticket_id: int, attempt: int) -> Path:
    return log_root() / "tickets" / f"ticket-{int(ticket_id)}-attempt-{int(attempt)}.log"


def _redact(message: str) -> str:
    for name, value in os.environ.items():
        if name.upper().endswith(_SECRET_SUFFIXES) and len(value) >= 8:
            message = message.replace(value, "[redacted]")
    return message


def write_line(path: Path, message: str, level: str = "info", now: datetime | None = None) -> bool:
    """Append one timestamped line; return False (never raise) when the file cannot be written."""
    global _warned
    try:
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        text = _redact(" ".join(str(message).splitlines()) if message else "")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} [{level}] {text}\n")
        return True
    except OSError as e:
        if not _warned:
            _warned = True
            print(f"Warning: could not write log files ({e}). Continuing without them.",
                  file=sys.stderr)
        return False


def read_log(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def prune_logs(max_age_days: int = RETENTION_DAYS, now: datetime | None = None) -> int:
    """Delete run and attempt logs older than ``max_age_days``; return how many were removed."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)).timestamp()
    deleted = 0
    for sub in ("runs", "tickets"):
        try:
            files = list((log_root() / sub).iterdir())
        except OSError:
            continue
        for f in files:
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    deleted += 1
            except OSError:
                continue
    return deleted
