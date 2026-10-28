"""Phase 7 AC-2: the Resumes tab has an always-visible Add resume form (checked in the served page source)."""

import pytest

from p7_helpers import Client, start_server, stop_server


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    from hireember.database import close_connection, init_db

    db = tmp_path_factory.mktemp("p7ui") / "hireember.db"
    init_db(db)
    server, thread = start_server(db)
    status, _, payload = Client(server.server_address[1]).request("GET", "/")
    stop_server(server, thread)
    close_connection(db)
    assert status == 200
    return payload.decode("utf-8")


def test_form_controls_and_labels(page):
    assert 'accept=".pdf,.txt,.docx"' in page
    for label in ("File", "Name", "Tags"):
        assert f'"aria-label": "{label}"' in page or f'aria-label="{label}"' in page, label
    assert "Add resume" in page


def test_upload_states_and_toast(page):
    assert "Adding..." in page
    assert "Resume added." in page
    assert "/api/resumes" in page and "X-Filename" in page


def test_empty_state_text(page):
    assert "No resumes yet. Add one with the form above or with 'hireember resume add'." in page
    assert "No resumes yet. Add one with 'hireember resume add'." not in page

