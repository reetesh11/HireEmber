"""AC-2, AC-3, AC-4, AC-5 (changed part): location matching with regions belonging to countries."""

import pytest

from hireember.location import location_skip_reason

CANADA = {"personal": {"country": "Canada"}}
ALBERTA = {"personal": {"province_state": "Alberta"}}
US = {"personal": {"country": "United States"}}


def skip(location, profile=None, cfg=None):
    return location_skip_reason(location, profile, {} if cfg is None else cfg)


@pytest.mark.parametrize("text", ["Calgary, AB", "Toronto, ON", "Vancouver, British Columbia",
                                  "Yellowknife, NT", "Whitehorse, Yukon"])
def test_ac2_country_target_canada_accepts_every_canadian_region(text):
    assert skip(text, CANADA) is None


def test_ac2_country_given_as_accept_entry_behaves_like_profile_country():
    cfg = {"location": {"accept_patterns": ["Canada"]}}
    assert skip("Calgary, AB", None, cfg) is None
    assert skip("Austin, TX", None, cfg) == "location: Austin, TX"


@pytest.mark.parametrize("text", ["Austin, TX", "Washington, DC", "Portland, Oregon"])
def test_us_target_accepts_every_us_state_and_dc(text):
    assert skip(text, US) is None


def test_region_target_accepts_country_only_text_of_its_country():
    assert skip("Calgary, Canada", ALBERTA) is None


@pytest.mark.parametrize("text", ["Calgary", "Greater Toronto Area"])
@pytest.mark.parametrize("profile", [CANADA, ALBERTA])
def test_ac4_text_with_no_recognised_region_or_country_is_not_skipped(text, profile):
    assert skip(text, profile) is None


def test_unrecognised_other_country_text_is_not_skipped():
    assert skip("Berlin, Germany", CANADA) is None


def test_ac4_bare_ca_passes_for_canada_and_for_california():
    assert skip("CA", CANADA) is None
    assert skip("CA", {"personal": {"province_state": "California"}}) is None
    assert skip("CA", None, {"location": {"accept_patterns": ["California"]}}) is None


def test_multi_part_text_passes_if_any_part_passes():
    assert skip("Austin, TX; Calgary, AB", CANADA) is None
    assert skip("Austin, TX | London, UK", CANADA) == "location: Austin, TX | London, UK"


def test_ac5_updated_phase_0e_cases_unrecognised_text_no_longer_skipped():
    profile = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
    cfg = {"locations": [{"location": "Toronto, ON", "remote": False}]}
    assert location_skip_reason("Berlin, Germany", profile, cfg) is None
    assert location_skip_reason("Paris, France", profile, cfg) is None
    assert location_skip_reason("Remote - Germany", profile, cfg) is None

