"""AC-3: scoring ensures exactly one ticket per role, pending or skipped by threshold."""

import pytest

from hireember.database import close_connection, init_db, store_jobs


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    store_jobs(c, [{"url": "u7", "title": "A"}, {"url": "u6", "title": "B"}], "S", "t")
    yield c
    close_connection(db)


def _tickets(conn, url):
    return conn.execute("SELECT * FROM tickets WHERE job_url=?", (url,)).fetchall()


def test_scores_7_and_6_give_pending_and_skipped(conn):
    from hireember.tickets import get_history, get_ticket, set_job_score

    t7 = set_job_score(conn, "u7", 7, "good")
    t6 = set_job_score(conn, "u6", 6, "meh")
    assert get_ticket(conn, t7)["status"] == "pending"
    assert get_ticket(conn, t6)["status"] == "skipped"
    assert len(_tickets(conn, "u7")) == 1 and len(_tickets(conn, "u6")) == 1
    assert get_history(conn, t7)[0]["reason"] == "score 7 meets threshold 7"
    assert get_history(conn, t6)[0]["reason"] == "score 6 below threshold 7"
    assert get_history(conn, t7)[0]["actor"] == "system"


def test_rescoring_creates_no_second_ticket(conn):
    from hireember.tickets import get_ticket, set_job_score

    t7 = set_job_score(conn, "u7", 7)
    t6 = set_job_score(conn, "u6", 6)
    assert set_job_score(conn, "u7", 7) == t7
    assert set_job_score(conn, "u7", 2) == t7
    assert set_job_score(conn, "u6", 9) == t6
    assert len(_tickets(conn, "u7")) == 1 and len(_tickets(conn, "u6")) == 1
    assert get_ticket(conn, t7)["status"] == "pending"
    assert get_ticket(conn, t6)["status"] == "skipped"


def test_threshold_setting_changes_outcome(conn):
    from hireember.tickets import get_ticket, get_threshold, set_job_score, set_setting

    assert get_threshold(conn) == 7
    set_setting(conn, "score_threshold", "8")
    assert get_threshold(conn) == 8
    assert get_ticket(conn, set_job_score(conn, "u7", 7))["status"] == "skipped"


@pytest.mark.parametrize("value", ["", "abc"])
def test_bad_threshold_falls_back_to_7(conn, value):
    from hireember.tickets import get_threshold, set_setting

    set_setting(conn, "score_threshold", value)
    assert get_threshold(conn) == 7
