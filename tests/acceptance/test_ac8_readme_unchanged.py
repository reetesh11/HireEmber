"""AC-8 (unchanged behaviour): upstream attribution and the License section stay."""

from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"


def test_readme_keeps_license_section_and_upstream_attribution():
    text = README.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    assert "## License" in lines
    assert "GNU Affero General Public License v3.0" in text
    assert "[Pickle-Pixel](https://github.com/Pickle-Pixel)" in text
