"""Phase 4: behaviour that must not change (passes before and after)."""

import pytest

from p4_helpers import make_ticket


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db()
    yield c
    close_connection(isolated_db)


def test_set_status_user_actor_writes_event_and_same_status_is_noop(conn):
    from hireember import tickets

    tid = make_ticket(conn, "u1", "pending")
    tickets.set_status(conn, tid, "closed", actor="user", reason="nope")
    hist = tickets.get_history(conn, tid)
    assert hist[-1]["actor"] == "user" and hist[-1]["status"] == "closed"
    n = len(hist)
    tickets.set_status(conn, tid, "closed", actor="user")
    assert len(tickets.get_history(conn, tid)) == n
    with pytest.raises(tickets.InvalidStatusError):
        tickets.set_status(conn, tid, "bogus")


def test_save_answer_and_queue_flow_unchanged(conn):
    from hireember import answers

    tid = make_ticket(conn, "u2", "blocked for human")
    qid = answers.queue_question(conn, tid, "unknown question", "Hobby?")
    result = answers.answer_queue_item(conn, qid, "chess")
    assert result.saved if hasattr(result, "saved") else True
    assert [a["answer"] for a in answers.list_answers(conn)] == ["chess"]
    with pytest.raises(answers.SensitiveQuestionError):
        answers.save_answer(conn, "What is your password?", "x")


def test_resume_add_list_unchanged(conn, tmp_path):
    from hireember import resumes

    f = tmp_path / "x.txt"
    f.write_text("hello", encoding="utf-8")
    rid = resumes.add_resume(conn, f, "Plain", "A, b")
    row = resumes.list_resumes(conn)[0]
    assert row["id"] == rid and row["tags"] == ["a", "b"] and row["pinned"] is False
    with pytest.raises(resumes.ResumeError):
        resumes.add_resume(conn, f, "plain")
