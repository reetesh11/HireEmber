"""Phase 2 AC-3: answering a queued question stores it, resolves the item, resumes the ticket."""

import pytest
from typer.testing import CliRunner

from hireember.database import close_connection, init_db

from p2_helpers import add_job, widen_cli_console

Q = "What is your favourite colour?"


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    tid = add_job(conn, "https://j.example/1")
    yield conn, tid
    close_connection(db)


def _blocked(conn, tid, question=Q):
    from hireember.answers import match_answer

    return match_answer(conn, tid, question).queue_item_id


def test_answer_stores_resolves_and_resumes(env):
    from hireember.answers import answer_queue_item, list_answers, list_queue
    from hireember.tickets import get_history, get_ticket

    conn, tid = env
    item = _blocked(conn, tid)
    res = answer_queue_item(conn, item, "Blue")
    assert res.saved is True and res.ticket_id == tid
    assert res.message == f"Answer saved. Ticket {tid} is ready to resume."
    rows = list_answers(conn)
    assert len(rows) == 1
    assert rows[0]["answer"] == "Blue" and rows[0]["source"] == "user"
    assert rows[0]["question_text"] == Q
    assert conn.execute("SELECT resolved_at FROM queue_items WHERE id=?", (item,)).fetchone()[0]
    assert get_ticket(conn, tid)["status"] == "pending"
    last = get_history(conn, tid)[-1]
    assert (last["status"], last["actor"], last["reason"]) == ("pending", "user", "answered queued question")
    assert list_queue(conn) == []
    assert [i["id"] for i in list_queue(conn, include_resolved=True)] == [item]


def test_later_lookup_returns_answer_and_counts_use(env):
    from hireember.answers import answer_queue_item, list_answers, match_answer

    conn, tid = env
    answer_queue_item(conn, _blocked(conn, tid), "Blue")
    assert list_answers(conn)[0]["times_used"] == 0
    assert list_answers(conn)[0]["last_used_at"] is None
    res = match_answer(conn, tid, "what is your favourite colour")
    assert res.status == "answered" and res.answer == "Blue"
    row = list_answers(conn)[0]
    assert row["times_used"] == 1 and row["last_used_at"]
    first_used = row["last_used_at"]
    match_answer(conn, tid, Q)
    row = list_answers(conn)[0]
    assert row["times_used"] == 2 and row["last_used_at"] >= first_used


def test_blank_answer_rejected_and_item_stays_open(env):
    from hireember.answers import QueueError, answer_queue_item, list_answers, list_queue

    conn, tid = env
    item = _blocked(conn, tid)
    with pytest.raises(QueueError) as exc:
        answer_queue_item(conn, item, "   ")
    assert str(exc.value) == "Answer cannot be empty."
    assert [i["id"] for i in list_queue(conn)] == [item]
    assert list_answers(conn) == []


def test_unknown_or_resolved_item_rejected_without_change(env):
    from hireember.answers import QueueError, answer_queue_item, list_answers

    conn, tid = env
    with pytest.raises(QueueError) as exc:
        answer_queue_item(conn, 999, "x")
    assert str(exc.value) == "Queue item 999 not found or already resolved."
    item = _blocked(conn, tid)
    answer_queue_item(conn, item, "Blue")
    with pytest.raises(QueueError) as exc:
        answer_queue_item(conn, item, "Green")
    assert str(exc.value) == f"Queue item {item} not found or already resolved."
    assert [a["answer"] for a in list_answers(conn)] == ["Blue"]


def test_answer_replaces_existing_bank_entry(env):
    from hireember.answers import answer_queue_item, list_answers, save_answer

    conn, tid = env
    save_answer(conn, Q, "Red", "import")
    # a conflict-free replacement: queue the same question via the queue step on its own
    from hireember.answers import queue_question
    item = queue_question(conn, tid, "conflicting answers", Q)
    answer_queue_item(conn, item, "Blue")
    rows = list_answers(conn)
    assert [(r["answer"], r["source"]) for r in rows] == [("Blue", "user")]


def test_cli_queue_list_and_answer(env, isolated_db, monkeypatch):
    from hireember.cli import app

    conn, tid = env  # env's database file is the one isolated_db points the CLI at
    widen_cli_console(monkeypatch)
    runner = CliRunner()
    item = _blocked(conn, tid)

    listed = runner.invoke(app, ["queue", "list"])
    assert listed.exit_code == 0, listed.output
    for word in ("Id", "Ticket", "Kind", "Question", "unknown question", Q):
        assert word in listed.output

    done = runner.invoke(app, ["queue", "answer", str(item), "Blue"])
    assert done.exit_code == 0, done.output
    assert f"Answer saved. Ticket {tid} is ready to resume." in done.output

    again = runner.invoke(app, ["queue", "answer", str(item), "Blue"])
    assert again.exit_code == 1
    assert f"Queue item {item} not found or already resolved." in again.output

    empty = runner.invoke(app, ["queue", "list"])
    assert empty.exit_code == 0 and "No open queue items." in empty.output

    shown = runner.invoke(app, ["answers", "list"])
    assert shown.exit_code == 0, shown.output
    for word in ("Answers", "Question", "Key", "Answer", "Source", "Last used", "Used", "Blue", "user"):
        assert word in shown.output
