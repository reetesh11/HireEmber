"""Base resumes: stored copies, pinning and choosing the best fit for a job."""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

from hireember import config
from hireember.tickets import _now, normalize_text

NO_TEXT = "base resume has no text version"


class ResumeError(Exception):
    """A base resume operation failed."""


def _dir() -> Path:
    path = config.APP_DIR / "base_resumes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_tags(tags: str) -> str:
    seen: list[str] = []
    for tag in (tags or "").split(","):
        tag = tag.strip().lower()
        if tag and tag not in seen:
            seen.append(tag)
    return ",".join(seen)


def _check_file(file: str | Path) -> Path:
    path = Path(file)
    if not path.is_file():
        raise ResumeError(f"File not found: {file}.")
    if path.suffix.lower() not in (".txt", ".pdf"):
        raise ResumeError("Unsupported format. Provide a .txt or .pdf file.")
    return path


def _store(src: Path, name: str, text_file: str | Path | None) -> Path:
    """Copy the file (and a PDF's text copy) into the base resume folder; return the copy."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "resume"
    suffix = src.suffix.lower()
    target = _dir() / f"{slug}{suffix}"
    n = 1
    while target.exists() or target.with_suffix(".txt").exists():
        n += 1
        target = _dir() / f"{slug}_{n}{suffix}"
    if suffix == ".pdf" and text_file and not Path(text_file).is_file():
        raise ResumeError(f"File not found: {text_file}.")
    shutil.copy2(src, target)
    if suffix == ".pdf" and text_file:
        shutil.copy2(text_file, target.with_suffix(".txt"))
    return target


def _remove(file_path: str) -> None:
    path = Path(file_path)
    path.unlink(missing_ok=True)
    if path.suffix.lower() == ".pdf":
        path.with_suffix(".txt").unlink(missing_ok=True)


def _row(conn: sqlite3.Connection, resume_id: int):
    row = conn.execute("SELECT id, name, tags, file_path, pinned, added_at FROM resumes WHERE id = ?",
                       (resume_id,)).fetchone()
    if row is None:
        raise ResumeError(f"No resume with id {resume_id}.")
    return row


def add_resume(conn: sqlite3.Connection, file: str | Path, name: str, tags: str = "",
               text_file: str | Path | None = None) -> int:
    src = _check_file(file)
    clean = (name or "").strip()
    if conn.execute("SELECT 1 FROM resumes WHERE lower(trim(name)) = ?", (clean.lower(),)).fetchone():
        raise ResumeError(f'A resume named "{name}" already exists.')
    target = _store(src, clean, text_file)
    cur = conn.execute(
        "INSERT INTO resumes (name, tags, file_path, pinned, added_at) VALUES (?, ?, ?, 0, ?)",
        (clean, _normalize_tags(tags), str(target), _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_resumes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, name, tags, file_path, pinned, added_at FROM resumes ORDER BY id")
    return [
        {"id": r[0], "name": r[1], "tags": [t for t in (r[2] or "").split(",") if t],
         "pinned": bool(r[4]), "file_path": r[3], "added_at": r[5]}
        for r in rows.fetchall()
    ]


def pin_resume(conn: sqlite3.Connection, resume_id: int) -> None:
    _row(conn, resume_id)
    conn.execute("UPDATE resumes SET pinned = CASE WHEN id = ? THEN 1 ELSE 0 END", (resume_id,))
    conn.commit()


def unpin_resume(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE resumes SET pinned = 0")
    conn.commit()


def get_resume_text(conn: sqlite3.Connection, resume_id: int) -> str:
    path = Path(_row(conn, resume_id)[3])
    if path.suffix.lower() != ".txt":
        path = path.with_suffix(".txt")
    if not path.is_file():
        raise ResumeError(NO_TEXT)
    return path.read_text(encoding="utf-8")


def choose_resume(conn: sqlite3.Connection, job: dict) -> int | None:
    """The pinned resume, else the one whose tags overlap the job title most (ties: lowest id)."""
    resumes = list_resumes(conn)
    if not resumes:
        return None
    for r in resumes:
        if r["pinned"]:
            return r["id"]
    words = set(normalize_text(job.get("title")).split())
    best, best_overlap = resumes[0]["id"], -1
    for r in resumes:
        tag_words = {w for t in r["tags"] for w in normalize_text(t).split()}
        overlap = len(tag_words & words)
        if overlap > best_overlap:
            best, best_overlap = r["id"], overlap
    return best


def update_resume(conn: sqlite3.Connection, resume_id: int, file: str | Path,
                  text_file: str | Path | None = None) -> None:
    """Replace the stored file of a base resume. Tickets and tailored files are never touched."""
    row = _row(conn, resume_id)
    src = _check_file(file)
    _remove(row[3])
    target = _store(src, row[1], text_file)
    conn.execute("UPDATE resumes SET file_path = ? WHERE id = ?", (str(target), resume_id))
    conn.commit()


def update_resume_meta(conn: sqlite3.Connection, resume_id: int, name: str | None = None,
                       tags: str | None = None) -> None:
    """Rename a base resume and/or replace its tags; ``None`` leaves a field as it is."""
    _row(conn, resume_id)
    if name is not None:
        clean = name.strip()
        if not clean:
            raise ResumeError("Name cannot be empty.")
        if conn.execute("SELECT 1 FROM resumes WHERE lower(trim(name)) = ? AND id != ?",
                        (clean.lower(), resume_id)).fetchone():
            raise ResumeError(f'A resume named "{name}" already exists.')
        conn.execute("UPDATE resumes SET name = ? WHERE id = ?", (clean, resume_id))
    if tags is not None:
        conn.execute("UPDATE resumes SET tags = ? WHERE id = ?", (_normalize_tags(tags), resume_id))
    conn.commit()
