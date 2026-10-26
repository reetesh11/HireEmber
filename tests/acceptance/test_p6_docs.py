"""Phase 6 AC-5: README setup path, and the section 7 safety rules in CONTRIBUTING and docs/safety.md."""

import re

import pytest

from p6_helpers import REPO_ROOT, heading_section

README = REPO_ROOT / "README.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
SAFETY = REPO_ROOT / "docs" / "safety.md"
SAF_IDS = [f"SAF-{n}" for n in range(1, 13)]
SETUP = r"Setup to your first scored role"


def _setup_section() -> str:
    section = heading_section(README.read_text(encoding="utf-8"), SETUP)
    assert section, "README.md has no 'Setup to your first scored role' heading"
    return section


def test_readme_setup_section_goes_from_install_to_a_scored_role():
    section = _setup_section()
    steps = re.findall(r"^\s*\d+\.\s+(.*)$", section, re.MULTILINE)
    assert len(steps) >= 5, f"expected a numbered list of at least 5 steps, found {len(steps)}"
    low = section.split("\n", 1)[1].lower()  # without the heading line
    for needle in ("install", "hireember init", "discover", "score", "dashboard"):
        assert needle in low, f"setup section does not mention {needle!r}"


def test_readme_setup_needs_no_code_edit():
    low = _setup_section().lower()
    assert not re.search(r"edit (the )?(code|source|python)|src/hireember|\.py\b", low)


def test_readme_says_schedules_do_not_fire_while_asleep():
    low = README.read_text(encoding="utf-8").lower()
    assert "do not fire while the machine" in low
    assert "asleep" in low or "sleeps" in low


@pytest.mark.parametrize("path, title_re", [(CONTRIBUTING, r"^Safety rules$"), (SAFETY, r"^Safety$")])
def test_safety_docs_exist_and_cover_the_section_7_rules(path, title_re):
    assert path.is_file(), f"{path.relative_to(REPO_ROOT)} does not exist"
    text = path.read_text(encoding="utf-8")
    assert heading_section(text, title_re), f"{path.name} has no heading matching {title_re}"
    for phrase in ("LinkedIn", "human gate", "telemetry", ".env"):
        assert phrase in text, f"{path.name} does not mention {phrase!r}"
    missing = [i for i in SAF_IDS if not re.search(rf"\b{i}\b", text)]
    assert missing == [], f"{path.name} does not mention {missing}"


def test_safety_page_title_and_contributing_docs_rule():
    assert SAFETY.is_file(), "docs/safety.md does not exist"
    assert SAFETY.read_text(encoding="utf-8").lstrip().startswith("# Safety")
    contributing = CONTRIBUTING.read_text(encoding="utf-8")
    assert "NFR-12" in contributing
    assert re.search(r"same (PR|pull request)", contributing, re.IGNORECASE)
