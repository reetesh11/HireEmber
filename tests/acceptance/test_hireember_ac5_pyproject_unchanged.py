"""Rename AC-5 (unchanged behaviour): version, upstream URLs and authors stay as they are."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_version_urls_and_authors_unchanged():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["version"] == "0.3.0"
    assert project["authors"] == [{"name": "Pickle-Pixel"}]
    assert project["urls"] == {
        "Homepage": "https://github.com/Pickle-Pixel/ApplyPilot",
        "Repository": "https://github.com/Pickle-Pixel/ApplyPilot",
        "Issues": "https://github.com/Pickle-Pixel/ApplyPilot/issues",
    }
