import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "acceptance"))

from p1_helpers import add_job  # noqa: E402

from hireember.database import close_connection, init_db  # noqa: E402
from hireember.tickets import (  # noqa: E402
    DuplicateTicketError,
    OverrideReasonError,
    get_history,
    get_ticket,
    set_status,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def test_site_fallback_when_no_company(conn):
    a = add_job(conn, "https://j.example/a", company=None)
    b = add_job(conn, "https://j.example/b", company=None)
    set_status(conn, a, "started")
    with pytest.raises(DuplicateTicketError):
        set_status(conn, b, "started")


def test_override_on_unblocked_ticket_with_blank_reason_is_ignored_without_match(conn):
    a = add_job(conn, "https://j.example/a", company="One", title="X", location="L")
    set_status(conn, a, "started", actor="user", override_reason="  ")
    assert get_ticket(conn, a)["status"] == "started"


def test_override_refused_leaves_blocked_ticket_untouched(conn):
    a = add_job(conn, "https://j.example/a")
    b = add_job(conn, "https://j.example/b")
    set_status(conn, a, "started")
    with pytest.raises(DuplicateTicketError):
        set_status(conn, b, "started")
    n = len(get_history(conn, b))
    with pytest.raises(OverrideReasonError):
        set_status(conn, b, "started", override_reason=" ")
    assert len(get_history(conn, b)) == n
    assert get_ticket(conn, b)["status"] == "blocked for human"


def test_self_is_not_a_duplicate(conn):
    a = add_job(conn, "https://j.example/a")
    set_status(conn, a, "started")
    set_status(conn, a, "applying")
    assert get_ticket(conn, a)["duplicate_of"] is None
