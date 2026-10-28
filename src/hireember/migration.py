"""Database schema additions, backup and ticket migration for HireEmber."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from hireember.tickets import normalize_text

NEW_TABLES: tuple[str, ...] = (
    "companies", "tickets", "ticket_events", "queue_items",
    "answers", "resumes", "runs", "settings",
)

NEW_JOBS_COLUMNS: tuple[str, ...] = (
    "company_id", "title_normalized", "location_normalized", "last_seen_at",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    careers_url TEXT,
    ats_type TEXT,
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY,
    job_url TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    status_reason TEXT DEFAULT '',
    resume_id INTEGER,
    tailored_resume_path TEXT,
    cover_letter_path TEXT,
    score INTEGER,
    score_reason TEXT,
    duplicate_of INTEGER,
    unverified INTEGER DEFAULT 0,
    referral_note TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS ticket_events (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    status TEXT,
    actor TEXT,
    reason TEXT DEFAULT '',
    link TEXT,
    link_kind TEXT,
    time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS queue_items (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER,
    kind TEXT,
    reason TEXT,
    page_link TEXT,
    question_text TEXT,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY,
    question_text TEXT,
    normalized_key TEXT,
    answer TEXT,
    source TEXT,
    times_used INTEGER DEFAULT 0,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY,
    name TEXT,
    tags TEXT,
    file_path TEXT,
    pinned INTEGER DEFAULT 0,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    kind TEXT,
    started_at TEXT,
    ended_at TEXT,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket ON ticket_events(ticket_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_updated ON tickets(updated_at);
"""


class MigrationError(RuntimeError):
    """The migration could not run safely."""


_ATTEMPT_LOG = """
CREATE TABLE IF NOT EXISTS attempt_log (
    id INTEGER PRIMARY KEY,
    ticket_id INTEGER NOT NULL,
    attempt INTEGER NOT NULL,
    time TEXT NOT NULL,
    kind TEXT NOT NULL,
    field TEXT DEFAULT '',
    source TEXT DEFAULT '',
    detail TEXT DEFAULT ''
)
"""

_PHASE3_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "companies": (("manual_only", "INTEGER DEFAULT 0"),),
    "tickets": (
        ("not_before", "TEXT"),
        ("submitted_at", "TEXT"),
        ("confirmation_link", "TEXT"),
        ("session_link", "TEXT"),
        ("resume_link", "TEXT"),
        ("notes", "TEXT"),
        ("referral_note", "TEXT"),
    ),
}


def ensure_phase3_schema(conn: sqlite3.Connection) -> None:
    """Add the apply-stage columns and the attempt log (idempotent, additive)."""
    for table, columns in _PHASE3_COLUMNS.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    conn.execute(_ATTEMPT_LOG)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attempt_log_ticket ON attempt_log(ticket_id)")
    conn.commit()


_PHASE5_RUN_COLUMNS: tuple[tuple[str, str], ...] = (
    ('"trigger"', "TEXT"), ("status", "TEXT"),
    ("found", "INTEGER DEFAULT 0"), ("scored", "INTEGER DEFAULT 0"),
    ("skipped", "INTEGER DEFAULT 0"), ("tickets_created", "INTEGER DEFAULT 0"),
    ("tickets_blocked", "INTEGER DEFAULT 0"),
)

_RUN_LOCK = """
CREATE TABLE IF NOT EXISTS run_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pid INTEGER,
    token TEXT,
    run_id INTEGER,
    acquired_at TEXT
)
"""

_RUN_LOG = """
CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY,
    run_id INTEGER,
    time TEXT,
    source TEXT,
    level TEXT,
    message TEXT
)
"""


def ensure_phase5_schema(conn: sqlite3.Connection) -> None:
    """Add run summary columns, the single-run lock and the run log (idempotent, additive)."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    for name, ddl in _PHASE5_RUN_COLUMNS:
        if name.strip('"') not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {ddl}")
    conn.execute(_RUN_LOCK)
    conn.execute(_RUN_LOG)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_log_run ON run_log(run_id)")
    conn.commit()


_STAGE_USAGE = """CREATE TABLE IF NOT EXISTS stage_usage (
    ticket_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    model TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (ticket_id, stage)
)"""


def ensure_phase6_schema(conn: sqlite3.Connection) -> None:
    """Add the per-ticket stage usage table (idempotent, additive)."""
    conn.execute(_STAGE_USAGE)
    conn.commit()


_RESUME_CHUNKS = """CREATE TABLE IF NOT EXISTS resume_chunks (
    id INTEGER PRIMARY KEY,
    resume_id INTEGER NOT NULL,
    section TEXT NOT NULL,
    position INTEGER NOT NULL,
    text TEXT NOT NULL
)"""

_RESUME_FTS = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS resume_chunks_fts USING fts5("
    "text, content='resume_chunks', content_rowid='id')",
    """CREATE TRIGGER IF NOT EXISTS resume_chunks_ai AFTER INSERT ON resume_chunks BEGIN
        INSERT INTO resume_chunks_fts(rowid, text) VALUES (new.id, new.text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS resume_chunks_ad AFTER DELETE ON resume_chunks BEGIN
        INSERT INTO resume_chunks_fts(resume_chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    END""",
    """CREATE TRIGGER IF NOT EXISTS resume_chunks_au AFTER UPDATE ON resume_chunks BEGIN
        INSERT INTO resume_chunks_fts(resume_chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
        INSERT INTO resume_chunks_fts(rowid, text) VALUES (new.id, new.text);
    END""",
]


def ensure_phase7_schema(conn: sqlite3.Connection) -> None:
    """Add resume extraction status columns and the chunk store with its FTS5 index (idempotent)."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(resumes)")}
    for name in ("extract_status", "extract_reason"):
        if name not in existing:
            conn.execute(f"ALTER TABLE resumes ADD COLUMN {name} TEXT")
    conn.execute(_RESUME_CHUNKS)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resume_chunks_resume ON resume_chunks(resume_id)")
    try:
        for stmt in _RESUME_FTS:
            conn.execute(stmt)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(f"SQLite FTS5 is required for the resume library but is unavailable: {exc}") from exc
    conn.commit()


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the eight new tables and indexes (idempotent), then the phase 3 and 5 additions."""
    for stmt in _SCHEMA.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    conn.commit()
    ensure_phase3_schema(conn)
    ensure_phase5_schema(conn)
    ensure_phase6_schema(conn)
    ensure_phase7_schema(conn)


def backfill_jobs(conn: sqlite3.Connection) -> None:
    """Fill normalized title/location and last_seen_at for rows that lack them."""
    rows = conn.execute(
        "SELECT url, title, location FROM jobs "
        "WHERE title_normalized IS NULL OR location_normalized IS NULL"
    ).fetchall()
    for url, title, location in rows:
        conn.execute(
            "UPDATE jobs SET title_normalized = ?, location_normalized = ? WHERE url = ?",
            (normalize_text(title), normalize_text(location), url),
        )
    conn.execute("UPDATE jobs SET last_seen_at = discovered_at WHERE last_seen_at IS NULL")
    conn.commit()


# old apply_status -> (ticket status, first event reason); None reason = use apply_error
_STATUS_MAP: dict[str, tuple[str, str | None]] = {
    "": ("pending", ""),
    "tailored": ("pending", ""),
    "in_progress": ("pending", "stale lock from an interrupted run"),
    "applied": ("applied", "unverified"),
    "failed": ("blocked for human", None),
    "manual": ("blocked for human", "manual ATS"),
    "captcha": ("blocked for human", "CAPTCHA"),
    "login_issue": ("blocked for human", "account needed"),
    "expired": ("closed", "role expired"),
}


def map_apply_status(apply_status: str | None, apply_error: str | None) -> tuple[str, str]:
    """Return (ticket status, reason) for an old ``apply_status`` value."""
    key = (apply_status or "").strip()
    if key not in _STATUS_MAP:
        return "blocked for human", f"unknown status: {key}"
    status, reason = _STATUS_MAP[key]
    return status, (apply_error or "") if reason is None else reason


def migrate_tickets(conn: sqlite3.Connection) -> int:
    """Create a ticket (and first event) for each tailored or attempted job lacking one.

    One transaction per ticket, so an interrupted run is completed by running again.
    Returns the number of tickets created.
    """
    rows = conn.execute(
        "SELECT j.url, j.apply_status, j.apply_error, j.fit_score, j.score_reasoning, "
        "j.tailored_resume_path, j.cover_letter_path FROM jobs j "
        "WHERE (COALESCE(j.apply_status, '') != '' OR COALESCE(j.tailored_resume_path, '') != '') "
        "AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.job_url = j.url) ORDER BY j.rowid"
    ).fetchall()
    created = 0
    for url, apply_status, apply_error, score, score_reason, resume, cover in rows:
        status, reason = map_apply_status(apply_status, apply_error)
        now = datetime.now(timezone.utc).isoformat()
        try:
            cur = conn.execute(
                "INSERT INTO tickets (job_url, status, status_reason, tailored_resume_path, "
                "cover_letter_path, score, score_reason, unverified, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (url, status, reason, resume, cover, score, score_reason,
                 1 if status == "applied" else 0, now, now),
            )
            conn.execute(
                "INSERT INTO ticket_events (ticket_id, status, actor, reason, time) "
                "VALUES (?, ?, 'system', ?, ?)",
                (cur.lastrowid, status, reason, now),
            )
            conn.commit()
            created += 1
        except sqlite3.IntegrityError:
            conn.rollback()
    return created


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30)


def needs_migration(db_path: Path | str) -> bool:
    """True when an existing database file would be changed by the migration.

    Uses a separate read-only connection; never writes.
    """
    path = Path(db_path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    conn = _open_readonly(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "jobs" not in tables:
            return False
        if any(t not in tables for t in NEW_TABLES):
            return True
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        if any(c not in cols for c in NEW_JOBS_COLUMNS):
            return True
        if conn.execute(
            "SELECT 1 FROM jobs WHERE title_normalized IS NULL OR location_normalized IS NULL "
            "OR last_seen_at IS NULL AND discovered_at IS NOT NULL LIMIT 1"
        ).fetchone():
            return True
        if conn.execute(
            "SELECT 1 FROM jobs j WHERE (COALESCE(j.apply_status, '') != '' "
            "OR COALESCE(j.tailored_resume_path, '') != '') "
            "AND NOT EXISTS (SELECT 1 FROM tickets t WHERE t.job_url = j.url) LIMIT 1"
        ).fetchone():
            return True
        return False
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def backup_if_needed(db_path: Path | str) -> Path | None:
    """Copy the database next to itself when the migration would change it.

    Returns the backup path, or None when no backup was needed.
    Raises MigrationError (database untouched) if the backup cannot be written.
    """
    path = Path(db_path)
    if not needs_migration(path):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    n = 0
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.bak-{stamp}-{n}")
    src = dst = None
    try:
        src = _open_readonly(path)
        dst = sqlite3.connect(str(target))
        src.backup(dst)
    except (OSError, sqlite3.Error) as exc:
        if dst is not None:
            dst.close()
            dst = None
        target.unlink(missing_ok=True)
        raise MigrationError(f"Backup failed; the database was not changed: {exc}") from exc
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
    return target


def migrate_database(db_path: Path | str) -> Path | None:
    """Back up (if needed) and migrate the database; return the backup path or None."""
    from hireember.database import _init_db

    _, backup = _init_db(db_path)
    return backup
