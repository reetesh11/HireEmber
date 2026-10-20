import pytest

from hireember.location import location_skip_reason

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
CFG = {"locations": [{"location": "Toronto, ON", "remote": False}]}


@pytest.mark.parametrize("location, skipped", [
    ("Toronto, ON", False),
    ("Berlin, Germany", True),
    ("Quebec City, Québec, Canada", False),
    ("Chicago, IL", True),
    ("N/A", False),
    ("U.S.A.", True),
    ("Hybrid - Berlin", True),
    ("Berlin | Paris ; Toronto", False),
    ("", False),
])
def test_table(location, skipped):
    reason = location_skip_reason(location, PROFILE, CFG)
    assert (reason == f"location: {location}") if skipped else reason is None


def test_ca_does_not_match_chicago():
    assert location_skip_reason("Chicago, IL", {"personal": {"province_state": "CA"}}, {}) is not None


def test_only_reject_entries_skip_only_matches():
    cfg = {"location": {"reject_patterns": ["Calgary"]}}
    assert location_skip_reason("Berlin", {}, cfg) is None
    assert location_skip_reason("Calgary, AB", {}, cfg) is not None


def test_no_targets():
    assert location_skip_reason("Berlin", None, {}) is None
