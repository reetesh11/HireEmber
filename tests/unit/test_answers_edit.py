"""Answer edit, delete and merge (implementation tests)."""

import pytest

from hireember import answers
from hireember.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def test_update_and_blank_and_sensitive(conn):
    a = answers.save_answer(conn, "Q?", "A")
    answers.update_answer(conn, a, "Q2?", "B")
    row = answers.list_answers(conn)[0]
    assert (row["question_text"], row["answer"]) == ("Q2?", "B")
    with pytest.raises(answers.AnswerError):
        answers.update_answer(conn, a, "Q2?", " ")
    with pytest.raises(answers.SensitiveQuestionError):
        answers.update_answer(conn, a, "your password", "x")


def test_merge_sums_and_rejects_same_id(conn):
    k = answers.save_answer(conn, "Q one?", "A1")
    r = answers.save_answer(conn, "Q two?", "A2", replace=False)
    conn.execute("UPDATE answers SET times_used = 1 WHERE id = ?", (k,))
    conn.execute("UPDATE answers SET times_used = 4 WHERE id = ?", (r,))
    conn.commit()
    with pytest.raises(answers.AnswerError):
        answers.merge_answers(conn, k, k)
    assert len(answers.list_answers(conn)) == 2
    answers.merge_answers(conn, k, r, answer="A2")
    rows = answers.list_answers(conn)
    assert len(rows) == 1 and rows[0]["times_used"] == 5 and rows[0]["answer"] == "A2"


def test_delete(conn):
    a = answers.save_answer(conn, "Q?", "A")
    answers.delete_answer(conn, a)
    with pytest.raises(answers.AnswerError):
        answers.delete_answer(conn, a)
