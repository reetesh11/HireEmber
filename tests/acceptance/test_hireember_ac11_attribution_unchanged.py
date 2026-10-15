"""Rename AC-11 (unchanged behaviour): upstream credit, disclaimer, licence and LICENSE stay."""

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README = REPO_ROOT / "README.md"

DISCLAIMER = (
    "> **⚠️ ApplyPilot** is the original open-source project, created by "
    "[Pickle-Pixel](https://github.com/Pickle-Pixel) and first published on GitHub on **February 17, 2026**. "
    "We are **not affiliated** with applypilot.app, useapplypilot.com, or any other product using the "
    "\"ApplyPilot\" name. These sites are **not associated with this project** and may misrepresent what "
    "they offer. If you're looking for the autonomous, open-source job application agent — you're in the "
    "right place."
)
FORK_NOTICE = (
    "HireEmber/OpenApply is a fork of [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) by "
    "[Pickle-Pixel](https://github.com/Pickle-Pixel). It is distributed under the same license, AGPL-3.0 "
    "(GNU Affero General Public License v3.0), and the original copyright notices and attribution are kept intact."
)
LICENSE_SHA256 = "0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0"


def test_readme_keeps_disclaimer_fork_notice_and_license_section():
    text = README.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    assert DISCLAIMER in lines
    assert "## Fork notice" in lines
    assert FORK_NOTICE in text
    assert "## License" in lines
    assert "GNU Affero General Public License v3.0" in text


def test_license_file_is_byte_for_byte_unchanged():
    assert hashlib.sha256((REPO_ROOT / "LICENSE").read_bytes()).hexdigest() == LICENSE_SHA256
