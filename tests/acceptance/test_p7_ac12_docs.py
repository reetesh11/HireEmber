"""Phase 7 AC-12: README and docs/traceability.md cover the resume library."""

import re

import pytest

from p7_helpers import REPO_ROOT

README = (REPO_ROOT / "README.md")
TRACE = (REPO_ROOT / "docs" / "traceability.md")
PRIVACY = ("Resume text extraction and search run entirely on your machine. Resume text leaves it only "
           "inside the prompts the pipeline already sends to your configured model.")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r\n", "\n"))


def test_readme_privacy_note_verbatim():
    assert PRIVACY in _norm(README.read_text(encoding="utf-8"))


def test_readme_lists_formats_limit_and_no_ocr():
    text = _norm(README.read_text(encoding="utf-8"))
    for fmt in (".pdf", ".txt", ".docx"):
        assert fmt in text
    assert "10 MB" in text
    assert re.search(r"\bno OCR\b|OCR is not supported|without OCR", text, re.IGNORECASE)


@pytest.mark.parametrize("n", range(1, 8))
def test_traceability_lists_each_res_requirement(n):
    text = TRACE.read_text(encoding="utf-8")
    assert re.search(rf"(?<![\w-])RES-{n}(?![\w-])", text), f"RES-{n} is not listed as its own ID"


def test_traceability_res_rows_point_at_phase7_tests():
    text = TRACE.read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if re.search(r"(?<![\w-])RES-[1-7](?![\w-])", ln)]
    assert len(rows) >= 7
    assert all("tests/" in ln for ln in rows)
    assert any("p7" in ln for ln in rows)
