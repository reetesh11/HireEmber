"""AC-1: `ruff check .` passes at the repository root."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ruff_check_passes_on_whole_repo():
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "."],
        check=False,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, f"ruff check . failed:\n{proc.stdout}\n{proc.stderr}"
