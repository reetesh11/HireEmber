"""AC-9: docs/traceability.md maps the phase-0 requirements to tests."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACE = REPO_ROOT / "docs" / "traceability.md"
REQUIREMENTS = ("FR-DIS-2", "SAF-4", "FR-CLI-2", "NFR-1", "NFR-10", "NFR-11")
TEST_REF = re.compile(r"tests/[\w./-]+\.py(?:::[\w\[\]-]+)?|tests/[\w./-]+/")


def _table_rows() -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    rows: dict[str, list[str]] = {}
    for line in TRACE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not header:
            header = cells
            continue
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        rows[cells[0].strip("`* ")] = cells
    return header, rows


def test_traceability_table_maps_each_requirement_to_existing_tests():
    assert TRACE.is_file(), "docs/traceability.md does not exist"
    header, rows = _table_rows()
    assert header == ["Requirement", "Description", "Tests"]

    for req in REQUIREMENTS:
        assert req in rows, f"no row for {req}"
        tests_cell = rows[req][2]
        refs = TEST_REF.findall(tests_cell)
        assert refs, f"{req}: Tests cell names no path under tests/: {tests_cell!r}"
        for ref in refs:
            path = REPO_ROOT / ref.split("::")[0]
            assert path.exists(), f"{req}: {ref} does not exist"

    for req in ("NFR-1", "NFR-11"):
        assert ".github/workflows/ci.yml" in rows[req][2], f"{req} must also name the CI workflow"
