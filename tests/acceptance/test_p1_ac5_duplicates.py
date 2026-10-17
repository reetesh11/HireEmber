"""AC-5: duplicate detection blocks a second ticket from starting."""

import pytest

from hireember.database import close_connection, init_db

from p1_helpers import add_job


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def _pair(conn, **second):
    first = add_job(conn, "https://j.example/a", title="Senior Engineer (Remote)",
                    location="Berlin", company="Acme")
    kw = dict(title="  senior  engineer remote", location="berlin", company="ACME")
    kw.update(second)
    other = add_job(conn, "https://j.example/b", **kw)
    return first, other


def _assert_blocked(conn, first, second):
    from hireember.tickets import DuplicateTicketError, get_history, get_ticket, set_status

    before = len(get_history(conn, second))
    with pytest.raises(DuplicateTicketError) as exc:
        set_status(conn, second, "started")
    assert str(exc.value) == f"Ticket {second} is a duplicate of ticket {first}; not started."
    assert exc.value.ticket_id == second and exc.value.duplicate_of == first
    t = get_ticket(conn, second)
    assert t["status"] == "blocked for human"
    assert t["status_reason"] == "duplicate"
    assert t["duplicate_of"] == first
    history = get_history(conn, second)
    assert len(history) == before + 1
    last = history[-1]
    assert last["status"] == "blocked for human" and last["reason"] == "duplicate"
    assert last["actor"] == "system"
    assert last["link"] == str(first) and last["link_kind"] == "duplicate-of"


@pytest.mark.parametrize("blocking", ["started", "applying", "blocked for human", "applied"])
def test_text_key_match_blocks_for_each_blocking_status(conn, blocking):
    from hireember.tickets import set_status

    first, second = _pair(conn)
    set_status(conn, first, blocking)
    _assert_blocked(conn, first, second)


def test_same_application_url_blocks(conn):
    from hireember.tickets import set_status

    first = add_job(conn, "https://j.example/a", company="One", title="X", location="L1",
                    application_url="https://apply.example/shared")
    second = add_job(conn, "https://j.example/b", company="Two", title="Y", location="L2",
                     application_url="https://apply.example/shared")
    set_status(conn, first, "started")
    _assert_blocked(conn, first, second)


def test_application_url_falls_back_to_job_url(conn):
    from hireember.tickets import set_status

    first = add_job(conn, "https://j.example/a", company="One", title="X", location="L1")
    second = add_job(conn, "https://j.example/b", company="Two", title="Y", location="L2",
                     application_url="https://j.example/a")
    set_status(conn, first, "applied")
    _assert_blocked(conn, first, second)


@pytest.mark.parametrize("passive", ["pending", "skipped", "closed"])
def test_non_blocking_match_does_not_block(conn, passive):
    from hireember.tickets import get_ticket, set_status

    first, second = _pair(conn)
    set_status(conn, first, passive)
    set_status(conn, second, "started")
    assert get_ticket(conn, second)["status"] == "started"
    assert get_ticket(conn, second)["duplicate_of"] in (None, 0)


@pytest.mark.parametrize("different", [{"location": "Paris"}, {"company": "Globex"},
                                       {"title": "Data Analyst"}])
def test_partial_match_is_not_a_duplicate(conn, different):
    from hireember.tickets import get_ticket, set_status

    first, second = _pair(conn, **different)
    set_status(conn, first, "started")
    set_status(conn, second, "started")
    assert get_ticket(conn, second)["status"] == "started"


def test_empty_location_never_matches_on_text_key(conn):
    from hireember.tickets import get_ticket, set_status

    first = add_job(conn, "https://j.example/a", location="", company="Acme", title="Dev")
    second = add_job(conn, "https://j.example/b", location="", company="Acme", title="Dev")
    set_status(conn, first, "started")
    set_status(conn, second, "started")
    assert get_ticket(conn, second)["status"] == "started"


def test_oldest_blocking_match_is_linked(conn):
    from hireember.tickets import set_status

    first = add_job(conn, "https://j.example/a", title="Dev", location="Rome", company="Acme")
    mid = add_job(conn, "https://j.example/b", title="Dev", location="Rome", company="Acme")
    third = add_job(conn, "https://j.example/c", title="Dev", location="Rome", company="Acme")
    set_status(conn, mid, "applied")
    set_status(conn, first, "applying")
    _assert_blocked(conn, first, third)


def test_asking_again_is_refused_without_new_event(conn):
    from hireember.tickets import DuplicateTicketError, get_history, set_status

    first, second = _pair(conn)
    set_status(conn, first, "started")
    _assert_blocked(conn, first, second)
    n = len(get_history(conn, second))
    with pytest.raises(DuplicateTicketError):
        set_status(conn, second, "started")
    assert len(get_history(conn, second)) == n
