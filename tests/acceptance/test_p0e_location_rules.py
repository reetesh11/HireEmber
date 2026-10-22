"""AC-7, AC-8: the deterministic location check (hireember.location.location_skip_reason)."""

import pytest
import yaml

from hireember import config

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}
CFG = {"locations": [{"location": "Toronto, ON", "remote": False}]}
CFG_REMOTE = {"locations": [{"location": "Toronto, ON", "remote": True}]}


def skip(location, profile=PROFILE, cfg=CFG):
    from hireember.location import location_skip_reason

    return location_skip_reason(location, profile, cfg)


@pytest.mark.parametrize("location", ["Austin, TX", "  London,  UK ", "Chicago, IL, USA", "London, UK"])
def test_ac7_recognised_location_matching_nothing_is_skipped(location):
    assert skip(location) == f"location: {location}"


@pytest.mark.parametrize(
    "location",
    ["Toronto, ON, Canada", "TORONTO,  on", "Ottawa, ON", "Ontario", "Vancouver, BC, Canada", "Canada",
     "Berlin, Germany; Toronto, ON", "Berlin, Germany | Calgary, AB, Canada"],
)
def test_ac8_matches_accept_province_country_or_one_of_several(location):
    assert skip(location) is None


def test_ac8_recognised_city_in_users_province_not_in_accept_list_is_kept():
    cfg = {"location": {"accept_patterns": ["Toronto"]}}
    assert skip("Mississauga, ON", PROFILE, cfg) is None


def test_several_locations_all_failing_is_skipped_with_full_string():
    text = "Austin, TX | London, UK"
    assert skip(text) == f"location: {text}"


@pytest.mark.parametrize("location", [None, "", "   ", "N/A", "nan", "None", "TBD", "Various", "Multiple Locations",
                                      "Unknown", "Worldwide", "Global", "12345", "--"])
def test_ac8_empty_and_unrecognisable_locations_are_not_skipped(location):
    assert skip(location) is None


def test_no_targets_at_all_means_no_skip():
    assert skip("Berlin, Germany", {}, {}) is None
    assert skip("Berlin, Germany", None, {}) is None


def test_ac8_remote_passes_when_remote_is_accepted():
    assert skip("Remote", PROFILE, CFG_REMOTE) is None
    assert skip("Remote - US", PROFILE, CFG_REMOTE) is None
    assert skip("Berlin, Germany (Remote)", PROFILE, CFG_REMOTE) is None


def test_remote_accepted_through_accept_entry():
    cfg = {"location": {"accept_patterns": ["remote", "Toronto"]}}
    assert skip("Remote - Germany", PROFILE, cfg) is None


def test_remote_not_accepted_checks_the_remainder_only():
    assert skip("Remote") is None  # empty remainder passes
    assert skip("Hybrid, Toronto") is None
    assert skip("Hybrid, Austin, TX") == "location: Hybrid, Austin, TX"
    assert skip("Remote - UK") == "location: Remote - UK"
    assert skip("Austin, TX (Remote)") == "location: Austin, TX (Remote)"


def test_reject_entry_skips_even_when_country_matches():
    cfg = {"location": {"accept_patterns": ["Toronto"], "reject_patterns": ["Calgary"]}}
    assert skip("Calgary, AB, Canada", PROFILE, cfg) == "location: Calgary, AB, Canada"
    cfg = {"location_reject_non_remote": ["Calgary"]}
    assert skip("Calgary, AB, Canada", PROFILE, cfg) == "location: Calgary, AB, Canada"


def test_top_level_accept_entries_are_used():
    cfg = {"location_accept": ["Berlin"]}
    assert skip("Berlin, Germany", {}, cfg) is None
    assert skip("London, UK", {}, cfg) == "location: London, UK"


def test_matching_is_whole_word_so_ca_does_not_match_chicago():
    profile = {"personal": {"province_state": "CA"}}
    assert skip("Chicago, IL", profile, {}) == "location: Chicago, IL"
    assert skip("Los Angeles, CA", profile, {}) is None


def test_abbreviations_match_full_names():
    profile = {"personal": {"province_state": "Ontario", "country": "United States"}}
    assert skip("Somewhere, ON", profile, {}) is None
    assert skip("Austin, TX, USA", profile, {}) is None
    assert skip("Austin, TX, US", profile, {}) is None
    profile = {"personal": {"province_state": "ON", "country": "USA"}}
    assert skip("Windsor, Ontario", profile, {}) is None
    assert skip("Austin, TX, United States", profile, {}) is None


def test_search_cfg_none_loads_searches_file(monkeypatch, tmp_path):
    from hireember.location import location_skip_reason

    cfg_path = tmp_path / "searches.yaml"
    cfg_path.write_text(yaml.safe_dump({"location": {"accept_patterns": ["Berlin"]}}), encoding="utf-8")
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", cfg_path)
    assert location_skip_reason("Berlin, Germany", {}) is None
    assert location_skip_reason("London, UK", {}) == "location: London, UK"


def test_search_cfg_none_with_missing_or_unreadable_file_uses_profile_only(monkeypatch, tmp_path):
    from hireember.location import location_skip_reason

    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "absent.yaml")
    assert location_skip_reason("Austin, TX", PROFILE) == "location: Austin, TX"
    assert location_skip_reason("Toronto, ON", PROFILE) is None
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed", encoding="utf-8")
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", bad)
    assert location_skip_reason("Austin, TX", PROFILE) == "location: Austin, TX"
