"""Phase 2 AC-2: browser-free answer matching, unknown and conflicting questions."""

import pytest

from hireember.database import close_connection, init_db

from p2_helpers import add_job

Q = "Are you authorized to work in the US?"


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    tid = add_job(conn, "https://j.example/1")
    yield conn, tid
    close_connection(db)


def _queue(conn):
    rows = conn.execute("SELECT id, ticket_id, kind, reason, question_text, resolved_at "
                        "FROM queue_items ORDER BY id").fetchall()
    return [dict(zip(r.keys(), tuple(r))) for r in rows]


def test_constants():
    from hireember import answers

    assert answers.KIND_UNKNOWN == "unknown question"
    assert answers.KIND_CONFLICT == "conflicting answers"
    assert answers.KIND_SENSITIVE == "sensitive question"


def test_known_question_returns_bank_answer_with_normalized_match(env):
    from hireember.answers import match_answer, save_answer
    from hireember.tickets import get_ticket

    conn, tid = env
    save_answer(conn, Q, "Yes", "profile")
    res = match_answer(conn, tid, "  are you AUTHORIZED to work in the us  ")
    assert res.status == "answered" and res.answer == "Yes"
    assert get_ticket(conn, tid)["status"] == "pending"
    assert _queue(conn) == []


def test_unknown_question_blocks_ticket_and_queues(env):
    from hireember.answers import match_answer
    from hireember.tickets import get_history, get_ticket

    conn, tid = env
    res = match_answer(conn, tid, "What is your favourite colour?")
    assert res.status == "unknown" and res.answer is None
    t = get_ticket(conn, tid)
    assert t["status"] == "blocked for human" and t["status_reason"] == "unknown question"
    q = _queue(conn)
    assert len(q) == 1
    assert q[0]["ticket_id"] == tid and q[0]["kind"] == "unknown question"
    assert q[0]["reason"] == "unknown question"
    assert q[0]["question_text"] == "What is your favourite colour?"
    assert q[0]["resolved_at"] is None
    assert res.queue_item_id == q[0]["id"]
    last = get_history(conn, tid)[-1]
    assert last["status"] == "blocked for human" and last["reason"] == "unknown question"


def test_conflicting_answers_block_and_queue(env):
    from hireember.answers import match_answer, save_answer
    from hireember.tickets import get_ticket

    conn, tid = env
    save_answer(conn, Q, "Yes", "profile")
    save_answer(conn, "are you authorized to work in the US", "No", "import", replace=False)
    res = match_answer(conn, tid, Q)
    assert res.status == "conflict" and res.answer is None
    t = get_ticket(conn, tid)
    assert t["status"] == "blocked for human" and t["status_reason"] == "conflicting answers"
    q = _queue(conn)
    assert len(q) == 1 and q[0]["kind"] == "conflicting answers"
    assert q[0]["question_text"] == Q and q[0]["ticket_id"] == tid


def test_identical_values_count_as_one_match(env):
    from hireember.answers import list_answers, match_answer, save_answer
    from hireember.tickets import get_ticket

    conn, tid = env
    save_answer(conn, Q, "Yes", "profile")
    save_answer(conn, Q.lower(), " yes ", "import", replace=False)
    res = match_answer(conn, tid, Q)
    assert res.status == "answered" and res.answer == "Yes"
    rows = list_answers(conn)
    assert [r["times_used"] for r in rows] == [1, 0]
    assert get_ticket(conn, tid)["status"] == "pending"
    assert _queue(conn) == []


def test_same_question_queued_twice_for_a_ticket_keeps_one_open_item(env):
    from hireember.answers import list_queue, match_answer, queue_question

    conn, tid = env
    first = match_answer(conn, tid, "What is your favourite colour?")
    second = match_answer(conn, tid, "what is your FAVOURITE colour")
    assert first.queue_item_id == second.queue_item_id
    assert len(_queue(conn)) == 1
    again = queue_question(conn, tid, "unknown question", "What is your favourite colour??")
    assert again == first.queue_item_id
    assert [i["id"] for i in list_queue(conn)] == [first.queue_item_id]


def test_queue_item_listing_shape(env):
    from hireember.answers import list_queue, match_answer

    conn, tid = env
    match_answer(conn, tid, "Why us?")
    items = list_queue(conn)
    assert len(items) == 1
    assert {"id", "ticket_id", "kind", "reason", "question_text", "resolved_at"} <= set(items[0])
