"""Rename AC-3: no module under src or tests imports the old package name."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD = "apply" + "pilot"
# Same lines as: grep -rnE "import <old>|from <old>" src tests
PATTERN = re.compile(r"import " + OLD + r"|from " + OLD)


def _text_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue


def test_no_imports_of_old_package_in_src_or_tests():
    hits = []
    for top in ("src", "tests"):
        for path, text in _text_files(REPO_ROOT / top):
            for n, line in enumerate(text.splitlines(), 1):
                if PATTERN.search(line):
                    hits.append(f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()}")
    assert hits == [], "old package still imported:\n" + "\n".join(hits)
