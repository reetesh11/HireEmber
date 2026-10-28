"""Resume text extraction (local PDF reading) and conservative profile proposals."""

from __future__ import annotations

import re
from pathlib import Path

MIN_TEXT_CHARS = 200

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_%-]+", re.I)
_PHONE = re.compile(r"(?<![\w.])\+?\(?\d[\d \t().-]{5,}\d(?![\w])")
_YEAR_RANGE = re.compile(r"^\s*(?:19|20)\d\d\s*[-.]\s*(?:19|20)\d\d\s*$")
_NAME_WORD = re.compile(r"^[^\W\d_](?:[^\W\d_]|[-'.])*$")
_SEPARATORS = re.compile(r"[|•·]")


def extract_pdf_text(path: str | Path) -> str:
    """All pages' text joined with newlines; "" on any failure. Local only."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            return ""
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def extract_docx_text(path: str | Path) -> str:
    """Body paragraphs and table cells in document order (cells tab-joined). Local only.

    Raises ValueError("this .docx file could not be read.") on a corrupt or unreadable file.
    """
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(str(path))
        lines: list[str] = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                lines.append(Paragraph(child, doc).text)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    lines.append("\t".join(cell.text.replace("\n", " ") for cell in row.cells))
        return "\n".join(lines)
    except Exception as exc:
        raise ValueError("this .docx file could not be read.") from exc


def _single(matches: list[str], key=lambda s: s.lower()) -> str | None:
    distinct = {key(m) for m in matches}
    return matches[0] if len(distinct) == 1 else None


def _name(lines: list[str]) -> str | None:
    if not lines:
        return None
    line = lines[0]
    words = line.split()
    if not 2 <= len(words) <= 4 or any(c in line for c in "@/"):
        return None
    if all(_NAME_WORD.match(w) for w in words):
        return " ".join(words)
    return None


def _phone(text: str) -> str | None:
    cleaned = _LINKEDIN.sub(" ", _EMAIL.sub(" ", text))
    found = []
    for m in _PHONE.finditer(cleaned):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15 and not _YEAR_RANGE.match(raw):
            found.append((raw, digits))
    distinct = {d for _, d in found}
    return found[0][0] if len(distinct) == 1 else None


def _location(lines: list[str]) -> dict[str, str]:
    hits = []
    for line in lines[:10]:
        for segment in _SEPARATORS.split(line):
            parts = [p.strip() for p in segment.split(",")]
            if (len(parts) == 3 and all(parts) and not re.search(r"\d", segment)
                    and all(len(p.split()) <= 3 for p in parts)):
                hits.append(parts)
    if len(hits) != 1:
        return {}
    city, province, country = hits[0]
    return {"city": city, "province_state": province, "country": country}


def propose_profile(text: str) -> dict[str, str]:
    """Only confidently found fields; never a postal code. Never raises."""
    try:
        text = text or ""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        out: dict[str, str] = {}
        name = _name(lines)
        if name:
            out["full_name"] = name
        email = _single(_EMAIL.findall(text))
        if email:
            out["email"] = email
        phone = _phone(text)
        if phone:
            out["phone"] = phone
        linkedin = _single([m.group(0) for m in _LINKEDIN.finditer(text)],
                           key=lambda s: s.lower().rsplit("/in/", 1)[-1])
        if linkedin:
            out["linkedin_url"] = linkedin
        out.update(_location(lines))
        return out
    except Exception:
        return {}
