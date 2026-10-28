"""Resume sections, chunking and local keyword search over an FTS5 index."""

from __future__ import annotations

import re
import sqlite3

SECTIONS = ("summary", "experience", "education", "skills", "other")
MAX_CHUNK_CHARS = 800
_PRE_HEADING_MAX = 600
_MAX_TERMS = 40

_HEADINGS = {
    "summary": "summary", "professional summary": "summary", "profile": "summary",
    "work experience": "experience", "experience": "experience", "employment": "experience",
    "education": "education",
    "skills": "skills", "technical skills": "skills",
}


def _heading(line: str) -> str | None:
    key = line.strip().rstrip(":").strip().lower()
    return _HEADINGS.get(key)


def split_sections(text: str) -> list[tuple[str, str]]:
    """(section, body) pairs in document order; empty sections are dropped."""
    parts: list[tuple[str, list[str]]] = []
    current: str | None = None
    lines: list[str] = []
    seen_heading = False
    for line in (text or "").splitlines():
        sec = _heading(line)
        if sec is not None:
            if not seen_heading:
                pre = "\n".join(lines).strip()
                if pre:
                    parts.append(("other" if len(pre) > _PRE_HEADING_MAX else "summary", lines))
            elif current is not None:
                parts.append((current, lines))
            seen_heading = True
            current, lines = sec, []
        else:
            lines.append(line)
    if seen_heading:
        parts.append((current, lines))
    else:
        parts.append(("other", lines))
    out = []
    for sec, body in parts:
        joined = "\n".join(body).strip()
        if joined:
            out.append((sec, joined))
    return out


def _split_long(line: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    cur = ""
    for word in line.split():
        while len(word) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur += " " + word
        else:
            pieces.append(cur)
            cur = word
    if cur:
        pieces.append(cur)
    return pieces


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack whole lines into chunks of at most ``max_chars``; over-long lines split on whitespace."""
    chunks: list[str] = []
    cur = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        for piece in ([line] if len(line) <= max_chars else _split_long(line, max_chars)):
            if not cur:
                cur = piece
            elif len(cur) + 1 + len(piece) <= max_chars:
                cur += "\n" + piece
            else:
                chunks.append(cur)
                cur = piece
    if cur:
        chunks.append(cur)
    return chunks


def delete_chunks(conn: sqlite3.Connection, resume_id: int) -> None:
    conn.execute("DELETE FROM resume_chunks WHERE resume_id = ?", (resume_id,))
    conn.commit()


def replace_chunks(conn: sqlite3.Connection, resume_id: int, text: str) -> int:
    """Replace the resume's chunks; returns how many were stored."""
    conn.execute("DELETE FROM resume_chunks WHERE resume_id = ?", (resume_id,))
    position = 0
    for section, body in split_sections(text):
        for chunk in chunk_text(body):
            conn.execute(
                "INSERT INTO resume_chunks (resume_id, section, position, text) VALUES (?, ?, ?, ?)",
                (resume_id, section, position, chunk))
            position += 1
    conn.commit()
    return position


def count_chunks(conn: sqlite3.Connection, resume_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM resume_chunks WHERE resume_id = ?", (resume_id,)).fetchone()[0]


def _match_query(query: str) -> str:
    terms: list[str] = []
    for tok in re.findall(r"\w+", (query or "").lower()):
        if tok not in terms:
            terms.append(tok)
        if len(terms) >= _MAX_TERMS:
            break
    return " OR ".join(f'"{t}"' for t in terms)


def search_chunks(conn: sqlite3.Connection, query: str, resume_id: int | None = None,
                  limit: int = 5) -> list[dict]:
    """Ranked chunks (best first); [] for unusable queries. Never raises on special characters."""
    match = _match_query(query)
    if not match or limit is None or limit <= 0:
        return []
    sql = ("SELECT c.id, c.resume_id, r.name, c.section, c.position, c.text, bm25(resume_chunks_fts) "
           "FROM resume_chunks_fts JOIN resume_chunks c ON c.id = resume_chunks_fts.rowid "
           "LEFT JOIN resumes r ON r.id = c.resume_id WHERE resume_chunks_fts MATCH ?")
    args: list = [match]
    if resume_id is not None:
        sql += " AND c.resume_id = ?"
        args.append(resume_id)
    sql += " ORDER BY bm25(resume_chunks_fts), c.id LIMIT ?"
    args.append(int(limit))
    try:
        rows = conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"chunk_id": r[0], "resume_id": r[1], "resume_name": r[2], "section": r[3],
             "position": r[4], "text": r[5], "score": -float(r[6])} for r in rows]
