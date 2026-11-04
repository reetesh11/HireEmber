"""Phase 9 AC-3: one location matcher; location_lists merges old and new keys in one place."""

import re
from pathlib import Path


import hireember

DISCOVERY = Path(hireember.__file__).parent / "discovery"


OLD = {"location_accept": ["Toronto", "Remote"], "location_reject_non_remote": ["Berlin"]}
NEW = {"location": {"accept_patterns": ["Toronto", "Remote"], "reject_patterns": ["Berlin"]}}


def test_location_ok_removed_from_discovery_modules():
    for name in ("jobspy", "workday", "smartextract"):
        text = (DISCOVERY / f"{name}.py").read_text(encoding="utf-8")
        assert "_location_ok" not in text, name
    for path in DISCOVERY.rglob("*.py"):
        assert not re.search(r"def\s+_?location_(ok|match)\w*", path.read_text(encoding="utf-8")), path


def test_location_lists_new_block_wins_without_union():
    from hireember.search_config import location_lists

    assert location_lists(OLD) == (["Toronto", "Remote"], ["Berlin"])
    assert location_lists(NEW) == (["Toronto", "Remote"], ["Berlin"])
    both = {**OLD, "location": {"accept_patterns": ["Paris"], "reject_patterns": ["Rome"]}}
    assert location_lists(both) == (["Paris"], ["Rome"])
