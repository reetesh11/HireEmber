"""Whole-word job title filtering and the init proposal for target roles and hard-no titles."""

from __future__ import annotations

import re
from collections.abc import Sequence

_SOFTWARE_RE = re.compile(r"engineer|developer|programmer|software", re.IGNORECASE)

_SOFTWARE_INCLUDE = ["software engineer", "engineer", "developer"]
_SOFTWARE_EXCLUDE = [
    "sales", "program manager", "account executive", "recruiter", "marketing",
    "customer success", "business development", "account manager", "talent acquisition",
    "human resources", "accountant", "paralegal",
]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _usable(entries: Sequence | None) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for entry in entries or []:
        if not isinstance(entry, str):
            continue
        text = entry.strip()
        words = _words(text)
        if text and words:
            out.append((text, words))
    return out


def _contains(words: list[str], phrase: list[str]) -> bool:
    n = len(phrase)
    return any(words[i:i + n] == phrase for i in range(len(words) - n + 1))


def title_filter(title: str | None, include: Sequence | None, exclude: Sequence | None) -> str | None:
    """Return None to keep the job, or ``title: <reason>`` when its title is filtered out."""
    words = _words(title) if isinstance(title, str) else []
    for text, phrase in _usable(exclude):
        if _contains(words, phrase):
            return f"title: {text}"
    inc = _usable(include)
    if inc and not any(_contains(words, phrase) for _, phrase in inc):
        return "title: not in target roles"
    return None


def _dedupe(items) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        if isinstance(item, str) and item.strip():
            seen.setdefault(item.strip().lower(), None)
    return list(seen)


def propose_title_lists(roles: Sequence[str], target_role: str = "",
                        resume_text: str = "") -> tuple[list[str], list[str]]:
    """Propose (include, exclude) title lists from roles, target role and resume text."""
    given = [*roles, target_role]
    software = any(isinstance(r, str) and _SOFTWARE_RE.search(r) for r in given) or bool(
        resume_text and _SOFTWARE_RE.search(resume_text))
    include = _dedupe(given + (_SOFTWARE_INCLUDE if software else []))
    exclude = _dedupe(_SOFTWARE_EXCLUDE) if software else []
    return include, exclude
