"""Shared helpers for the phase-1 data layer acceptance tests (public surfaces only)."""

import sqlite3

LEGACY_JOBS_SCHEMA = """
CREATE TABLE jobs (
    url TEXT PRIMARY KEY, title TEXT, salary TEXT, description TEXT, location TEXT,
    site TEXT, strategy TEXT, discovered_at TEXT,
    full_description TEXT, application_url TEXT, detail_scraped_at TEXT, detail_error TEXT,
    fit_score INTEGER, score_reasoning TEXT, scored_at TEXT,
    tailored_resume_path TEXT, tailored_at TEXT, tailor_attempts INTEGER DEFAULT 0,
    cover_letter_path TEXT, cover_letter_at TEXT, cover_attempts INTEGER DEFAULT 0,
    applied_at TEXT, apply_status TEXT, apply_error TEXT, apply_attempts INTEGER DEFAULT 0,
    agent_id TEXT, last_attempted_at TEXT, apply_duration_ms INTEGER, apply_task_id TEXT,
    verification_confidence TEXT
)
"""

# (url suffix, apply_status, tailored_resume_path, apply_error)
LEGACY_ROWS = [
    ("empty", None, "/r/empty.pdf", None),
    ("tailored", "tailored", "/r/tailored.pdf", None),
    ("in_progress", "in_progress", "/r/ip.pdf", None),
    ("applied", "applied", "/r/applied.pdf", None),
    ("failed", "failed", "/r/failed.pdf", "Timeout on submit button"),
    ("manual", "manual", "/r/manual.pdf", None),
    ("captcha", "captcha", "/r/captcha.pdf", None),
    ("login_issue", "login_issue", "/r/login.pdf", None),
    ("expired", "expired", "/r/expired.pdf", None),
]
UNTOUCHED_URL = "https://jobs.example/untouched"


def url_for(name: str) -> str:
    return f"https://jobs.example/{name}"


def make_legacy_db(path) -> None:
    """Create an old-style ApplyPilot database (jobs table only) at ``path``."""
    conn = sqlite3.connect(str(path))
    conn.execute(LEGACY_JOBS_SCHEMA)
    for name, status, resume, error in LEGACY_ROWS:
        conn.execute(
            "INSERT INTO jobs (url, title, location, site, fit_score, apply_status, "
            "tailored_resume_path, apply_error) VALUES (?,?,?,?,?,?,?,?)",
            (url_for(name), "  Senior  Engineer (Remote) " if name == "empty" else f"Title {name}",
             "New York, NY", "Acme", 8, status, resume, error),
        )
    conn.execute(
        "INSERT INTO jobs (url, title, location, site) VALUES (?,?,?,?)",
        (UNTOUCHED_URL, "Untouched", "Paris", "Acme"),
    )
    conn.commit()
    conn.close()


def table_names(conn) -> list[str]:
    return sorted(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def add_job(conn, url, *, title="Backend Engineer", location="Berlin", company="Acme",
            application_url=None, score=8):
    """Store one job via store_jobs, optionally set application_url, and score it."""
    from hireember.database import store_jobs
    from hireember.tickets import set_job_score

    job = {"url": url, "title": title, "location": location}
    if company is not None:
        job["company"] = company
    store_jobs(conn, [job], "TestSite", "test")
    if application_url is not None:
        conn.execute("UPDATE jobs SET application_url=? WHERE url=?", (application_url, url))
        conn.commit()
    return set_job_score(conn, url, score)
