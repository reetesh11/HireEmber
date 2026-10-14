"""AC-8: README has a fork notice (ApplyPilot, AGPL-3.0)."""

from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"


def _section(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == heading:
            body = []
            for nxt in lines[i + 1:]:
                if nxt.startswith(("## ", "# ")):
                    break
                body.append(nxt)
            return "\n".join(body)
    return None


def test_readme_has_fork_notice_section():
    section = _section(README.read_text(encoding="utf-8"), "## Fork notice")
    assert section is not None, "README.md has no '## Fork notice' section"
    assert "fork" in section.lower()
    assert "ApplyPilot" in section
    assert "https://github.com/Pickle-Pixel/ApplyPilot" in section
    assert "AGPL-3.0" in section
