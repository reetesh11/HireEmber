"""AC-5: remote, empty, placeholder and no-target behaviour is as in phase 0e (green before and after)."""

import pytest

from hireember.location import location_skip_reason

CANADA = {"personal": {"country": "Canada"}}
US = {"personal": {"country": "United States"}}
ALBERTA = {"personal": {"province_state": "Alberta"}}
CFG_REMOTE = {"locations": [{"location": "Toronto, ON", "remote": True}]}


@pytest.mark.parametrize("text", [None, "", "   ", "N/A", "TBD", "Various", "Worldwide", "Multiple Locations", "12345"])
def test_empty_and_placeholder_text_is_not_skipped(text):
    assert location_skip_reason(text, CANADA, {}) is None


def test_no_targets_means_no_skip():
    assert location_skip_reason("Austin, TX", {}, {}) is None
    assert location_skip_reason("Austin, TX", None, {}) is None


def test_remote_wording_passes_only_when_remote_is_accepted():
    assert location_skip_reason("Remote", CANADA, {}) is None
    assert location_skip_reason("Austin, TX (Remote)", CANADA, CFG_REMOTE) is None
    assert location_skip_reason("Austin, TX (Remote)", CANADA, {}) == "location: Austin, TX (Remote)"


def test_clearly_elsewhere_text_is_skipped_with_text_as_given():
    assert location_skip_reason("Austin, TX", CANADA, {}) == "location: Austin, TX"
    assert location_skip_reason("London, UK", CANADA, {}) == "location: London, UK"


def test_ac2_canadian_text_naming_canada_is_accepted_for_canada():
    assert location_skip_reason("Montreal, QC, Canada", CANADA, {}) is None


def test_us_target_accepts_text_naming_usa_and_skips_canadian_region():
    assert location_skip_reason("Boston, MA, USA", US, {}) is None
    assert location_skip_reason("Toronto, ON", US, {}) == "location: Toronto, ON"


def test_ac3_region_target_accepts_that_region_only():
    assert location_skip_reason("Calgary, AB", ALBERTA, {}) is None
    assert location_skip_reason("Toronto, ON", ALBERTA, {}) == "location: Toronto, ON"
    cfg = {"location": {"accept_patterns": ["Alberta"]}}
    assert location_skip_reason("Calgary, AB", None, cfg) is None
    assert location_skip_reason("Toronto, ON", None, cfg) == "location: Toronto, ON"


def test_ac4_bare_ca_is_skipped_when_only_target_is_texas():
    assert location_skip_reason("CA", {"personal": {"province_state": "Texas"}}, {}) == "location: CA"


def test_reject_patterns_still_skip_recognised_text():
    cfg = {"location": {"reject_patterns": ["Calgary"]}}
    assert location_skip_reason("Calgary, AB", CANADA, cfg) == "location: Calgary, AB"


def test_reject_patterns_still_apply_to_text_with_no_recognised_region():
    cfg = {"location": {"accept_patterns": ["Canada"], "reject_patterns": ["Calgary"]}}
    assert location_skip_reason("Calgary", CANADA, cfg) == "location: Calgary"
