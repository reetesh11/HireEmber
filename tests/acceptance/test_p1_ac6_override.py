"""AC-6: a user can override a duplicate block with a reason."""

import pytest

from hireember.database import close_connection, init_db

from p1_helpers import add_job


@pytest.fixture
def pair(tmp_path):
    from hireember.tickets import set_status

    db = tmp_path / "hireember.db"
    conn = init_db(db)
    first = add_job(conn, "https://j.example/a", title="Dev", location="Rome", company="Acme")
    second = add_job(conn, "https://j.example/b", title="Dev", location="Rome", company="Acme")
    set_status(conn, first, "started")
    yield conn, first, second
    close_connection(db)


def _check_override(conn, first, second):
    from hireember.tickets import get_history, get_ticket

    t = get_ticket(conn, second)
    assert t["status"] == "started"
    assert t["duplicate_of"] == first
    assert get_ticket(conn, first)["status"] == "started"
    history = get_history(conn, second)
    overrides = [h for h in history if h["link_kind"] == "override"]
    assert len(overrides) == 1
    assert overrides[0]["actor"] == "user"
    assert overrides[0]["reason"] == "reapplying"
    assert overrides[0]["link"] == str(first)
    assert history[-1]["status"] == "started"
    assert history.index(overrides[0]) < len(history) - 1


def test_override_lets_ticket_start(pair):
    from hireember.tickets import set_status

    conn, first, second = pair
    set_status(conn, second, "started", actor="user", override_reason="reapplying")
    _check_override(conn, first, second)


def test_override_after_block(pair):
    from hireember.tickets import DuplicateTicketError, set_status

    conn, first, second = pair
    with pytest.raises(DuplicateTicketError):
        set_status(conn, second, "started")
    set_status(conn, second, "started", actor="user", override_reason="reapplying")
    _check_override(conn, first, second)


@pytest.mark.parametrize("reason", ["", "   "])
def test_empty_override_reason_refused_and_nothing_written(pair, reason):
    from hireember.tickets import OverrideReasonError, get_history, get_ticket, set_status

    conn, _, second = pair
    before_status = get_ticket(conn, second)["status"]
    n = len(get_history(conn, second))
    with pytest.raises(OverrideReasonError) as exc:
        set_status(conn, second, "started", actor="user", override_reason=reason)
    assert str(exc.value) == "An override needs a reason."
    assert get_ticket(conn, second)["status"] == before_status
    assert len(get_history(conn, second)) == n
