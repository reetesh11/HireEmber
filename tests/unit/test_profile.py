"""Profile groups, schema and example file."""

import json
from pathlib import Path

from hireember.profile import PROFILE_GROUPS, PROFILE_SCHEMA, contains_key

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ten_groups_in_order():
    assert [g.key for g in PROFILE_GROUPS] == [
        "contact", "location", "work_authorization", "availability", "compensation",
        "experience_level", "target_roles", "skills_boundary", "resume_facts", "eeo"]
    assert [g.key for g in PROFILE_GROUPS if g.optional] == ["eeo"]


def test_no_password_in_schema_or_example():
    assert not contains_key(PROFILE_SCHEMA, "password")
    data = json.loads((REPO_ROOT / "profile.example.json").read_text(encoding="utf-8"))
    assert not contains_key(data, "password")


def test_contains_key_recursive_case_insensitive():
    assert contains_key([{"a": {"PassWord": 1}}], "password")
    assert not contains_key({"a": "password"}, "password")
