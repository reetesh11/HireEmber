import pytest

from hireember.apply.attempts import get_log, log_step, start_attempt
from hireember.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def test_attempt_numbers_count_up_per_ticket(conn):
    assert start_attempt(conn, 1) == 1
    log_step(conn, 1, 1, "start")
    assert start_attempt(conn, 1) == 2
    assert start_attempt(conn, 2) == 1


def test_log_is_oldest_first_with_all_keys(conn):
    log_step(conn, 1, 1, "start")
    log_step(conn, 1, 1, "fill", "Full name", "profile:full_name", "Test")
    rows = get_log(conn, 1)
    assert [r["kind"] for r in rows] == ["start", "fill"]
    assert set(rows[1]) == {"id", "attempt", "time", "kind", "field", "source", "detail"}
    assert rows[1]["source"] == "profile:full_name"
