"""Base resumes: stored copies, pinning and choosing the best fit for a job."""

from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hireember import config, resume_index
from hireember.resume_extract import extract_docx_text, extract_pdf_text
from hireember.tickets import _now, normalize_text

log = logging.getLogger(__name__)

NO_TEXT = "base resume has no text version"
UNSUPPORTED = "Unsupported format. Provide a .pdf, .txt or .docx file."
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SUFFIXES = (".txt", ".pdf", ".docx")

_REASON_DOCX = "this .docx file could not be read."
_REASON_PDF = "this PDF could not be read."
_REASON_MISSING = "The stored file is missing. Replace the file."
_REASON_SCANNED = "this looks like a scanned PDF. OCR is not supported. Add a text copy or a text-based PDF."
_REASON_EMPTY = "the file has no text."


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


@dataclass
class ExtractResult:
    status: str
    reason: str
    chunks: int


def _check_file(file: str | Path) -> Path:
    path = Path(file)
    if not path.is_file():
        raise ResumeError(f"File not found: {file}.")
    if path.suffix.lower() not in _SUFFIXES:
        raise ResumeError(UNSUPPORTED)
    size = path.stat().st_size
    if size == 0:
        raise ResumeError("The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise ResumeError("The file is larger than 10 MB.")
    return path


def _text_path(path: Path) -> Path:
    """Where a resume's plain-text version lives (the file itself for .txt)."""
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path
    if suffix == ".docx":
        return path.with_name(path.name + ".txt")
    return path.with_suffix(".txt")


def _store(src: Path, name: str, text_file: str | Path | None) -> Path:
    """Copy the file (and a PDF's text copy) into the base resume folder; return the copy."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "resume"
    suffix = src.suffix.lower()
    target = _dir() / f"{slug}{suffix}"
    n = 1
    while target.exists() or target.with_suffix(".txt").exists() or _text_path(target).exists():
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
    if path.suffix.lower() in (".pdf", ".docx"):
        _text_path(path).unlink(missing_ok=True)


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
    if not clean:
        raise ResumeError("Name cannot be empty.")
    if conn.execute("SELECT 1 FROM resumes WHERE lower(trim(name)) = ?", (clean.lower(),)).fetchone():
        raise ResumeError(f'A resume named "{name}" already exists.')
    target = _store(src, clean, text_file)
    cur = conn.execute(
        "INSERT INTO resumes (name, tags, file_path, pinned, added_at) VALUES (?, ?, ?, 0, ?)",
        (clean, _normalize_tags(tags), str(target), _now()),
    )
    conn.commit()
    _extract_quietly(conn, cur.lastrowid)
    return cur.lastrowid


def _upload_suffix(filename: str, data: bytes) -> str:
    """Validate a byte upload (extension, empty, size); return the lower-case extension."""
    base = re.split(r"[\\/]", filename or "")[-1]
    suffix = Path(base).suffix.lower()
    if suffix not in _SUFFIXES:
        raise ResumeError(UNSUPPORTED)
    if not data:
        raise ResumeError("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeError("The file is larger than 10 MB.")
    return suffix


def add_resume_bytes(conn: sqlite3.Connection, filename: str, data: bytes, name: str, tags: str = "") -> int:
    """Add a resume from uploaded bytes. Only the extension of ``filename`` is used."""
    suffix = _upload_suffix(filename, data)
    clean = (name or "").strip()
    if not clean:
        raise ResumeError("Name cannot be empty.")
    if conn.execute("SELECT 1 FROM resumes WHERE lower(trim(name)) = ?", (clean.lower(),)).fetchone():
        raise ResumeError(f'A resume named "{name}" already exists.')
    with tempfile.TemporaryDirectory(prefix="hireember-upload-") as tmp:
        src = Path(tmp) / f"upload{suffix}"
        src.write_bytes(data)
        return add_resume(conn, src, clean, tags)


def replace_resume_file_bytes(conn: sqlite3.Connection, resume_id: int, filename: str, data: bytes) -> None:
    _row(conn, resume_id)
    suffix = _upload_suffix(filename, data)
    with tempfile.TemporaryDirectory(prefix="hireember-upload-") as tmp:
        src = Path(tmp) / f"upload{suffix}"
        src.write_bytes(data)
        update_resume(conn, resume_id, src)


def list_resumes(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT r.id, r.name, r.tags, r.file_path, r.pinned, r.added_at, r.extract_status, r.extract_reason, "
        "(SELECT COUNT(*) FROM resume_chunks c WHERE c.resume_id = r.id) FROM resumes r ORDER BY r.id")
    return [
        {"id": r[0], "name": r[1], "tags": [t for t in (r[2] or "").split(",") if t],
         "pinned": bool(r[4]), "file_path": r[3], "added_at": r[5],
         "extract_status": r[6] or "not_extracted", "extract_reason": r[7] or "", "chunk_count": r[8]}
        for r in rows.fetchall()
    ]


def _fail(conn: sqlite3.Connection, resume_id: int, status: str, reason: str) -> ExtractResult:
    resume_index.delete_chunks(conn, resume_id)
    conn.execute("UPDATE resumes SET extract_status = ?, extract_reason = ? WHERE id = ?",
                 (status, reason, resume_id))
    conn.commit()
    return ExtractResult(status, reason, 0)


def _read_text(path: Path) -> tuple[str | None, str, str]:
    """(text, failure status, reason). ``text`` is None when extraction failed."""
    suffix = path.suffix.lower()
    if not path.is_file():
        return None, "failed", _REASON_MISSING
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="replace"), "", _REASON_EMPTY
    copy = _text_path(path)
    if suffix == ".docx":
        try:
            text = extract_docx_text(path)
        except ValueError:
            return None, "failed", _REASON_DOCX
        if text.strip():
            copy.write_text(text, encoding="utf-8")
        return text, "", _REASON_EMPTY
    # .pdf: a provided or earlier text copy wins, else read the PDF locally
    if copy.is_file():
        return copy.read_text(encoding="utf-8", errors="replace"), "", _REASON_SCANNED
    try:
        from pypdf import PdfReader

        PdfReader(str(path))
    except Exception:
        return None, "failed", _REASON_PDF
    text = extract_pdf_text(path)
    if text.strip():
        copy.write_text(text, encoding="utf-8")
    return text, "", _REASON_SCANNED


def extract_resume(conn: sqlite3.Connection, resume_id: int) -> ExtractResult:
    """Re-run text extraction and rebuild the resume's chunks. Never raises for file problems."""
    row = _row(conn, resume_id)
    try:
        text, status, reason = _read_text(Path(row[3]))
    except Exception as exc:
        log.debug("resume %s extraction error: %s", resume_id, type(exc).__name__)
        return _fail(conn, resume_id, "failed", "this file could not be read.")
    if text is None:
        return _fail(conn, resume_id, status, reason)
    if not text.strip():
        return _fail(conn, resume_id, "no_text", reason)
    count = resume_index.replace_chunks(conn, resume_id, text)
    if count == 0:
        return _fail(conn, resume_id, "no_text", _REASON_EMPTY)
    conn.execute("UPDATE resumes SET extract_status = 'extracted', extract_reason = '' WHERE id = ?",
                 (resume_id,))
    conn.commit()
    return ExtractResult("extracted", "", count)


def _extract_quietly(conn: sqlite3.Connection, resume_id: int) -> None:
    try:
        extract_resume(conn, resume_id)
    except Exception as exc:
        log.debug("resume %s extraction error: %s", resume_id, type(exc).__name__)


def delete_resume(conn: sqlite3.Connection, resume_id: int) -> None:
    """Remove a resume, its files and chunks; refused while a ticket uses it."""
    row = _row(conn, resume_id)
    used = conn.execute("SELECT COUNT(*) FROM tickets WHERE resume_id = ?", (resume_id,)).fetchone()[0]
    if used:
        raise ResumeError(f'Resume "{row[1]}" is used by {used} ticket(s) and cannot be deleted.')
    _remove(row[3])
    resume_index.delete_chunks(conn, resume_id)
    conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    conn.commit()


def search(conn: sqlite3.Connection, query: str, resume_id: int | None = None, limit: int = 5) -> list[dict]:
    """Keyword search over resume chunks, best first. Local only."""
    return resume_index.search_chunks(conn, query, resume_id=resume_id, limit=limit)


def pin_resume(conn: sqlite3.Connection, resume_id: int) -> None:
    _row(conn, resume_id)
    conn.execute("UPDATE resumes SET pinned = CASE WHEN id = ? THEN 1 ELSE 0 END", (resume_id,))
    conn.commit()


def unpin_resume(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE resumes SET pinned = 0")
    conn.commit()


def get_resume_text(conn: sqlite3.Connection, resume_id: int) -> str:
    path = _text_path(Path(_row(conn, resume_id)[3]))
    if not path.is_file():
        raise ResumeError(NO_TEXT)
    return path.read_text(encoding="utf-8", errors="replace")


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
    _extract_quietly(conn, resume_id)


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
