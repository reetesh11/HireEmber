"""Phase 9 AC-3/AC-4 behaviour that already holds and must not change: word-boundary location matching."""

import pytest

PROFILE = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}


def skip(location, cfg, profile=PROFILE):
    from hireember.location import location_skip_reason

    return location_skip_reason(location, profile, cfg)


OLD = {"location_accept": ["Toronto", "Remote"], "location_reject_non_remote": ["Berlin"]}
NEW = {"location": {"accept_patterns": ["Toronto", "Remote"], "reject_patterns": ["Berlin"]}}
SAMPLES = ["Toronto, ON", "Berlin, Germany", "Austin, TX", "Remote", "", "Calgary, AB", "Chicago, IL"]


@pytest.mark.parametrize("location", SAMPLES)
def test_old_and_new_keys_give_identical_results(location):
    assert skip(location, OLD) == skip(location, NEW)


@pytest.mark.parametrize("location", ["Chicago, IL", "Vacation Island, FL"])
def test_ca_does_not_match_inside_words(location):
    cfg = {"location": {"accept_patterns": ["CA"]}}
    assert skip(location, cfg, {}) == f"location: {location}"


@pytest.mark.parametrize("location", ["Toronto, CA", "Oakland, CA"])
def test_ca_matches_as_a_word(location):
    assert skip(location, {"location": {"accept_patterns": ["CA"]}}, {}) is None


def test_sf_not_in_transfer():
    cfg = {"location": {"accept_patterns": ["SF"]}}
    assert skip("Transfer, TX", cfg, {}) is not None
    assert skip("SF Bay Area", cfg, {}) is None


def test_calgary_passes_for_target_canada():
    assert skip("Calgary, AB", {"location": {"accept_patterns": ["Canada"]}}, PROFILE) is None
