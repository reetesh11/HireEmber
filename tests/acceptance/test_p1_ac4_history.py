"""AC-4: status changes write ordered history events; invalid statuses are rejected."""

import pytest

from hireember.database import close_connection, init_db

from p1_helpers import add_job


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    tid = add_job(conn, "https://j.example/1")
    yield conn, tid
    close_connection(db)


def test_history_has_one_event_per_change_in_order(env):
    from hireember.tickets import get_history, set_status

    conn, tid = env
    set_status(conn, tid, "started", reason="go")
    set_status(conn, tid, "applying", actor="user", reason="manual push")
    set_status(conn, tid, "applied", reason="done")
    history = get_history(conn, tid)
    assert [h["status"] for h in history] == ["pending", "started", "applying", "applied"]
    assert [h["actor"] for h in history][1:] == ["system", "user", "system"]
    assert [h["reason"] for h in history][1:] == ["go", "manual push", "done"]
    assert all(h["time"] for h in history)
    ids = [h["id"] for h in history]
    assert ids == sorted(ids)
    assert {"id", "ticket_id", "status", "actor", "reason", "link", "link_kind", "time"} <= set(history[0])


def test_same_status_is_not_a_change(env):
    from hireember.tickets import get_history, set_status

    conn, tid = env
    set_status(conn, tid, "pending")
    assert len(get_history(conn, tid)) == 1


def test_all_allowed_statuses_listed():
    from hireember.tickets import ALLOWED_STATUSES

    assert ALLOWED_STATUSES == ("pending", "started", "applying", "blocked for human",
                                "applied", "skipped", "closed")


def test_invalid_status_rejected_and_nothing_written(env):
    from hireember.tickets import InvalidStatusError, get_history, get_ticket, set_status

    conn, tid = env
    with pytest.raises(InvalidStatusError) as exc:
        set_status(conn, tid, "flying")
    assert "flying" in str(exc.value)
    assert "blocked for human" in str(exc.value)
    assert get_ticket(conn, tid)["status"] == "pending"
    assert len(get_history(conn, tid)) == 1


def test_invalid_actor_and_unknown_ticket(env):
    from hireember.tickets import TicketNotFoundError, set_status

    conn, tid = env
    with pytest.raises(ValueError):
        set_status(conn, tid, "closed", actor="robot")
    with pytest.raises(TicketNotFoundError) as exc:
        set_status(conn, 9999, "closed")
    assert str(exc.value) == "Ticket 9999 not found."
