"""Answer bank, matching and queue (implementation tests)."""

import pytest

from hireember import answers
from hireember.database import close_connection, init_db
from hireember.tickets import get_ticket, set_job_score


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    conn.execute("INSERT INTO jobs (url, title, site) VALUES ('https://j/1', 'T', 'S')")
    conn.commit()
    tid = set_job_score(conn, "https://j/1", 8, "ok")
    yield conn, tid
    close_connection(db)


def test_times_used_and_normalized_match(env):
    conn, tid = env
    answers.save_answer(conn, "Salary?", "100k", "profile")
    assert answers.match_answer(conn, tid, " salary ").answer == "100k"
    assert answers.list_answers(conn)[0]["times_used"] == 1


def test_conflict_vs_identical(env):
    conn, tid = env
    answers.save_answer(conn, "Q?", "A", "user")
    answers.save_answer(conn, "q", " a ", "import", replace=False)
    assert answers.match_answer(conn, tid, "Q").status == "answered"
    answers.save_answer(conn, "q!", "B", "import", replace=False)
    assert answers.match_answer(conn, tid, "Q").status == "conflict"
    assert get_ticket(conn, tid)["status_reason"] == "conflicting answers"


def test_sensitive_blocks_even_with_entry(env):
    conn, tid = env
    conn.execute("INSERT INTO answers (question_text, normalized_key, answer, source) "
                 "VALUES ('Your password', 'your password', 'x', 'import')")
    conn.commit()
    res = answers.match_answer(conn, tid, "Your password")
    assert res.status == "sensitive" and res.answer is None
    assert answers.answer_queue_item(conn, res.queue_item_id, "x").saved is False
    assert len(answers.list_answers(conn)) == 1


def test_queue_answer_errors_and_single_open_item(env):
    conn, tid = env
    a = answers.match_answer(conn, tid, "Why?")
    b = answers.match_answer(conn, tid, "why")
    assert a.queue_item_id == b.queue_item_id
    with pytest.raises(answers.QueueError, match="cannot be empty"):
        answers.answer_queue_item(conn, a.queue_item_id, " ")
    with pytest.raises(answers.QueueError, match="not found or already resolved"):
        answers.answer_queue_item(conn, 99, "x")
    res = answers.answer_queue_item(conn, a.queue_item_id, "Because")
    assert res.saved and get_ticket(conn, tid)["status"] == "pending"


def test_match_answer_returns_answer_id(env):
    conn, tid = env
    aid = answers.save_answer(conn, "Salary", "100k")
    assert answers.match_answer(conn, tid, "salary").answer_id == aid


def test_ready_and_answer_refuse_each_others_kinds(env):
    conn, tid = env
    cur = conn.execute("INSERT INTO queue_items (ticket_id, kind, reason, page_link, question_text) "
                       "VALUES (?, 'captcha', 'captcha', 'http://p', 'J')", (tid,))
    conn.commit()
    ready_id = cur.lastrowid
    question = answers.match_answer(conn, tid, "Why?").queue_item_id
    with pytest.raises(answers.QueueError, match='queue ready'):
        answers.answer_queue_item(conn, ready_id, "x")
    with pytest.raises(answers.QueueError, match='queue answer'):
        answers.ready_queue_item(conn, question)


def test_ready_sets_resume_link_and_list_queue_has_company_and_page(env):
    conn, tid = env
    cur = conn.execute("INSERT INTO queue_items (ticket_id, kind, reason, page_link, question_text) "
                       "VALUES (?, 'captcha', 'captcha', 'http://p', 'J')", (tid,))
    conn.commit()
    tickets_mod = answers.tickets
    tickets_mod.set_status(conn, tid, "blocked for human", reason="captcha")
    [row] = answers.list_queue(conn)
    assert row["page_link"] == "http://p" and row["company"] == "S"
    answers.ready_queue_item(conn, cur.lastrowid)
    t = get_ticket(conn, tid)
    assert t["status"] == "pending" and t["status_reason"] == "ready"
    assert t["resume_link"] == "http://p"
