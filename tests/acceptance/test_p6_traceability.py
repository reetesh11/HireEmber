"""Phase 6 AC-4: docs/traceability.md maps every FR, SAF and NFR ID to an existing test."""

import re

import pytest

from p6_helpers import REPO_ROOT, heading_section

REQUIREMENTS = REPO_ROOT / "OpenApply — Requirements Document.md"
TRACE = REPO_ROOT / "docs" / "traceability.md"
PARKED = REPO_ROOT / "docs" / "parked-fixes.md"
ID = re.compile(r"\b(?:FR|SAF|NFR)-(?:[A-Z]+-)?\d+\b")
REF = re.compile(r"`((?:tests/|\.github/workflows/)[^`\s:]*)(?:::([^`\s]+))?`")
SCOPE_MARK = re.compile(r"out of scope|later release|deferred", re.IGNORECASE)


def _requirement_ids() -> list[str]:
    assert REQUIREMENTS.is_file(), (
        "OpenApply — Requirements Document.md must be present at the repository root "
        "(commit it with this task); traceability is checked against it")
    ids = sorted(set(ID.findall(REQUIREMENTS.read_text(encoding="utf-8"))))
    assert len(ids) >= 70, f"expected about 75 requirement IDs, found {len(ids)}"
    return ids


def _tables(text: str) -> list[list[list[str]]]:
    """Every markdown table in ``text`` as rows of stripped cells (separator rows dropped)."""
    tables, current = [], []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                current.append(cells)
        elif current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _id_of(cell: str) -> str | None:
    m = ID.fullmatch(cell.strip("`* "))
    return m.group(0) if m else None


def _main_rows() -> list[list[str]]:
    assert TRACE.is_file(), "docs/traceability.md does not exist"
    for table in _tables(TRACE.read_text(encoding="utf-8")):
        if table[0] == ["Requirement", "Description", "Tests"]:
            return table[1:]
    pytest.fail("docs/traceability.md has no | Requirement | Description | Tests | table")


def _section_ids(heading: str) -> dict[str, list[str]]:
    section = heading_section(TRACE.read_text(encoding="utf-8"), rf"^{heading}$")
    assert section, f"docs/traceability.md has no '## {heading}' section"
    rows = {}
    for table in _tables(section):
        assert table[0] == ["Requirement", "Reason"], f"{heading}: header must be | Requirement | Reason |"
        for row in table[1:]:
            if _id_of(row[0]):
                rows[_id_of(row[0])] = row
    return rows


def test_every_requirement_id_is_in_the_table_exempt_or_known_exceptions():
    ids = _requirement_ids()
    main = {_id_of(r[0]) for r in _main_rows() if _id_of(r[0])}
    exempt, known = set(_section_ids("Exempt")), set(_section_ids("Known exceptions"))
    missing = [i for i in ids if i not in main | exempt | known]
    assert missing == [], f"no traceability entry for: {missing}"


def test_each_id_appears_once_and_only_ids_from_the_requirements_document_are_listed():
    ids = set(_requirement_ids())
    seen = []
    for row in _main_rows():
        assert _id_of(row[0]), f"first cell is not a requirement ID: {row[0]!r}"
        seen.append(_id_of(row[0]))
    seen += list(_section_ids("Exempt")) + list(_section_ids("Known exceptions"))
    dupes = sorted({i for i in seen if seen.count(i) > 1})
    assert dupes == [], f"IDs listed more than once: {dupes}"
    unknown = sorted(set(seen) - ids)
    assert unknown == [], f"IDs not in the requirements document: {unknown}"


def test_every_main_row_names_existing_test_files_and_test_names():
    ids = _requirement_ids()
    rows = _main_rows()
    listed = len(rows) + len(_section_ids("Exempt")) + len(_section_ids("Known exceptions"))
    assert listed >= len(ids), f"the table covers {listed} of {len(ids)} requirement IDs"
    problems = []
    for row in rows:
        req = _id_of(row[0])
        refs = REF.findall(row[2])
        if not refs:
            problems.append(f"{req}: Tests cell names no test under tests/ or .github/workflows/")
            continue
        for path, name in refs:
            target = REPO_ROOT / path
            if not target.exists():
                problems.append(f"{req}: {path} does not exist")
            elif name:
                bare = re.sub(r"\[.*\]$", "", name)
                if not target.is_file() or not re.search(rf"\bdef {re.escape(bare)}\b",
                                                         target.read_text(encoding="utf-8")):
                    problems.append(f"{req}: {path}::{name} not found")
    assert problems == [], "\n".join(problems)


def test_known_exceptions_are_listed_in_parked_fixes_with_a_reason():
    known = _section_ids("Known exceptions")
    parked = ""
    if known:
        assert PARKED.is_file(), "docs/parked-fixes.md does not exist"
        parked = heading_section(PARKED.read_text(encoding="utf-8"), r"^Traceability known exceptions$")
    missing = [i for i in known if i not in parked]
    assert missing == [], f"known exceptions missing from docs/parked-fixes.md: {missing}"
    assert all(row[1].strip() for row in known.values()), "every known exception needs a reason"


def test_exempt_ids_are_marked_later_or_out_of_scope_in_the_requirements_document():
    exempt = _section_ids("Exempt")
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines() if REQUIREMENTS.is_file() else []
    bad = []
    for req, row in exempt.items():
        mentions = [ln for ln in lines if re.search(rf"\b{re.escape(req)}\b", ln)]
        if not any(SCOPE_MARK.search(ln) for ln in mentions):
            bad.append(req)
        if not row[1].strip():
            bad.append(f"{req} (no reason)")
    assert bad == [], f"not marked later or out of scope: {bad}"
