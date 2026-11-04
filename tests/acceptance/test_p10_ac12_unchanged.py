"""Phase 10 AC-12 (unchanged behaviour): the dashboard has no control that turns review off."""

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


def test_no_control_turns_review_off(html):
    low = html.lower()
    assert "no-review" not in low and "review: false" not in low and "review:false" not in low
    assert '"review"' not in low.split("/api/jobs/add", 1)[-1][:600]
