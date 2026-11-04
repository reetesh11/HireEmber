"""Phase 9 AC-9: the Profile tab and the Tickets Restore action exist in the served dashboard page."""

import pytest

from p7_helpers import Client, start_server, stop_server


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    from hireember.database import close_connection, init_db

    db = tmp_path_factory.mktemp("p9ui") / "hireember.db"
    init_db(db)
    server, thread = start_server(db)
    status, _, payload = Client(server.server_address[1]).request("GET", "/")
    stop_server(server, thread)
    close_connection(db)
    assert status == 200
    return payload.decode("utf-8")


def test_profile_tab_and_section(page):
    assert "tab-profile" in page and "page-profile" in page
    assert "Profile" in page


@pytest.mark.parametrize("text", [
    "Loading profile...", "Could not load profile.",
    "Target roles", "Hard-no titles", "Target locations", "Rejected locations", "Where I live",
    "Matches whole words or phrases, ignoring case. 'sales' matches 'Sales Engineer' but not 'Salesforce Developer'.",
    "Remote jobs accepted", "City", "Region/State/Province", "Country",
    "Saved. The next discover run will use these values.", "Nothing was changed.", "Remove ",
])
def test_profile_texts(page, text):
    assert text in page


@pytest.mark.parametrize("ident", ["p-title_include", "p-title_exclude", "p-location_accept",
                                   "p-location_reject", "p-remote", "p-city", "p-province_state",
                                   "p-country", "/api/profile"])
def test_profile_control_ids(page, ident):
    assert ident in page


def test_restore_action_and_status_filter(page):
    assert "Restore" in page and "/restore" in page
    assert "f-status" in page and "All except dropped" in page
