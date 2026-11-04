"""Phase 10 AC-12: the Tickets tab has the Add job URLs panel, results table and blocked-ticket paste field."""

import pytest

from p10_helpers import Client, start_server, stop_server


@pytest.fixture(scope="module")
def html(tmp_path_factory):
    from hireember.database import close_connection, init_db

    db = tmp_path_factory.mktemp("p10ui") / "hireember.db"
    init_db(db)
    server, thread = start_server(db)
    status, _, payload = Client(server.server_address[1]).request("GET", "/")
    stop_server(server, thread)
    close_connection(db)
    assert status == 200
    return payload.decode("utf-8")


@pytest.mark.parametrize("text", [
    "Add job URLs", "Job URLs (one per line)", "Job description text (use if a page cannot be read)",
    "Add and apply", "A run is in progress.", "Adding ",
    "Enter at least one URL.", "You can add up to 25 URLs at a time.", "A URL is longer than 2048 characters.",
    "/api/jobs/add", "results", "Paste job description", "Continue", "/description",
])
def test_texts_and_endpoints(html, text):
    assert text in html


def test_status_and_alert_regions(html):
    panel = html.split("Add job URLs", 1)[1]
    assert 'role="status"' in panel and 'role="alert"' in panel


def test_results_table_headers(html):
    for header in ("URL", "Result", "Ticket", "Score", "Next step"):
        assert f">{header}<" in html or f"'{header}'" in html or f'"{header}"' in html, header
