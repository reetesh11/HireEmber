"""Phase 2 AC-4: stored answer fields, no password in profile files, sensitive questions never answered."""

import json

import pytest

from hireember.database import close_connection, init_db

from p2_helpers import REPO_ROOT, add_job

SENSITIVE = [
    "What is your password?",
    "Enter your API key",
    "Please provide your access token",
    "Credit card number",
    "CVV",
    "Bank account number",
    "What is your SSN?",
    "Social security number",
    "Passport number",
    "Government ID number",
]
NOT_SENSITIVE = [
    "Are you authorized to work in the US?",
    "What is your expected salary?",
    "Why do you want this job?",
]


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    tid = add_job(conn, "https://j.example/1")
    yield conn, tid
    close_connection(db)


def test_stored_answer_lists_all_fields(env):
    from hireember.answers import list_answers, normalize_question, save_answer
    from hireember.tickets import normalize_text

    conn, _ = env
    rid = save_answer(conn, "Are you authorized to work in the US?", "Yes", "profile")
    rows = list_answers(conn)
    assert len(rows) == 1 and rows[0]["id"] == rid
    row = rows[0]
    assert {"question_text", "normalized_key", "answer", "source", "last_used_at", "times_used"} <= set(row)
    assert row["question_text"] == "Are you authorized to work in the US?"
    assert row["normalized_key"] == "are you authorized to work in the us"
    assert normalize_question("A, b!  C?") == normalize_text("A, b!  C?")
    assert (row["answer"], row["source"], row["times_used"], row["last_used_at"]) == ("Yes", "profile", 0, None)


def test_save_answer_validation_and_replace(env):
    from hireember.answers import list_answers, save_answer

    conn, tid = env
    with pytest.raises(ValueError):
        save_answer(conn, "Q one?", "A", "robot")
    with pytest.raises(ValueError) as exc:
        save_answer(conn, "Q one?", "   ")
    assert str(exc.value) == "Answer cannot be empty."
    first = save_answer(conn, "Q one?", "A", "import")
    from hireember.answers import match_answer
    match_answer(conn, tid, "Q one?")
    assert save_answer(conn, "q one", "B", "user") == first
    rows = list_answers(conn)
    assert len(rows) == 1 and (rows[0]["answer"], rows[0]["source"], rows[0]["times_used"]) == ("B", "user", 1)
    other = save_answer(conn, "Q one?", "C", "user", replace=False)
    assert other != first and len(list_answers(conn)) == 2


def test_profile_example_json_has_no_password_key():
    from hireember.profile import contains_key

    data = json.loads((REPO_ROOT / "profile.example.json").read_text(encoding="utf-8"))
    assert not contains_key(data, "password")


def test_profile_schema_has_no_password_key():
    from hireember.profile import PROFILE_SCHEMA, contains_key

    assert isinstance(PROFILE_SCHEMA, dict) and PROFILE_SCHEMA
    assert not contains_key(PROFILE_SCHEMA, "password")


def test_contains_key_is_recursive_and_case_insensitive():
    from hireember.profile import contains_key

    assert contains_key({"a": [{"b": {"PassWord": 1}}]}, "password")
    assert not contains_key({"a": [{"b": {"pass": 1}}], "c": "password"}, "password")


@pytest.mark.parametrize("question", SENSITIVE)
def test_sensitive_questions_detected(question):
    from hireember.answers import is_sensitive

    assert is_sensitive(question)


@pytest.mark.parametrize("question", NOT_SENSITIVE)
def test_ordinary_questions_not_sensitive(question):
    from hireember.answers import is_sensitive

    assert not is_sensitive(question)


@pytest.mark.parametrize("question", SENSITIVE[:3] + SENSITIVE[6:8])
def test_sensitive_never_answered_even_with_bank_entry(env, question):
    from hireember.answers import match_answer, normalize_question
    from hireember.tickets import get_ticket

    conn, tid = env
    conn.execute("INSERT INTO answers (question_text, normalized_key, answer, source, times_used) "
                 "VALUES (?, ?, 'hunter2', 'import', 0)", (question, normalize_question(question)))
    conn.commit()
    res = match_answer(conn, tid, question)
    assert res.status == "sensitive" and res.answer is None
    t = get_ticket(conn, tid)
    assert t["status"] == "blocked for human" and t["status_reason"] == "sensitive question"
    q = conn.execute("SELECT kind, reason, question_text, resolved_at FROM queue_items").fetchall()
    assert [tuple(r) for r in q] == [("sensitive question", "sensitive question", question, None)]
    assert conn.execute("SELECT times_used FROM answers").fetchone()[0] == 0


def test_sensitive_cannot_be_saved(env):
    from hireember.answers import SensitiveQuestionError, list_answers, save_answer

    conn, _ = env
    with pytest.raises(SensitiveQuestionError):
        save_answer(conn, "What is your password?", "hunter2")
    assert issubclass(SensitiveQuestionError, ValueError)
    assert list_answers(conn) == []


def test_answering_sensitive_queue_item_does_not_store(env):
    from hireember.answers import answer_queue_item, list_answers, match_answer
    from hireember.tickets import get_ticket

    conn, tid = env
    item = match_answer(conn, tid, "What is your password?").queue_item_id
    res = answer_queue_item(conn, item, "hunter2")
    assert res.saved is False and res.ticket_id == tid
    assert res.message == ("Not saved: passwords, tokens, payment details and government IDs are "
                           f"never stored. Ticket {tid} stays blocked for human.")
    assert list_answers(conn) == []
    assert conn.execute("SELECT resolved_at FROM queue_items WHERE id=?", (item,)).fetchone()[0]
    assert get_ticket(conn, tid)["status"] == "blocked for human"
