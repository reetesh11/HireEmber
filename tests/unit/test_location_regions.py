import pytest

from hireember.location import location_skip_reason

CANADA = {"personal": {"country": "Canada"}}
ALBERTA = {"personal": {"province_state": "Alberta"}}


@pytest.mark.parametrize("text,profile,expected", [
    ("Montreal, QC, Canada", CANADA, None),
    ("Austin, TX", CANADA, "location: Austin, TX"),
    ("Los Angeles, CA, USA", CANADA, "location: Los Angeles, CA, USA"),
    ("Toronto, ON / New York, NY", CANADA, None),
    ("Washington, DC", {"personal": {"country": "USA"}}, None),
    ("Georgia", {"personal": {"country": "USA"}}, None),
    ("Calgary, Canada", ALBERTA, None),
    ("Toronto, ON, Canada", ALBERTA, "location: Toronto, ON, Canada"),
    ("CA", {"personal": {"province_state": "Texas"}}, "location: CA"),
])
def test_regions(text, profile, expected):
    assert location_skip_reason(text, profile, {}) == expected
