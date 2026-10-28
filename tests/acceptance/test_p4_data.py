"""Phase 4: data-layer additions and answer/resume editing, direct and over HTTP (AC-3, AC-8)."""

import pytest

from p4_helpers import Client, make_ticket, start_server, stop_server


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db()
    yield c
    close_connection(isolated_db)


@pytest.fixture
def api(isolated_db, conn):
    server, thread = start_server(isolated_db)
    yield Client(server.server_address[1])
    stop_server(server, thread)


def resume_file(tmp_path, name="cv.txt", text="resume body"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# -- AC-3: tickets.set_note -------------------------------------------------

def test_set_note_saves_text_and_writes_one_user_event(conn):
    from hireember import tickets

    tid = make_ticket(conn, "n1", "applied")
    before_ticket = tickets.get_ticket(conn, tid)
    before = len(tickets.get_history(conn, tid))
    tickets.set_note(conn, tid, "call back, \"soon\"")
    tickets.set_note(conn, tid, "Intro via Sam", kind="referral note")
    t = tickets.get_ticket(conn, tid)
    assert t["notes"] == "call back, \"soon\"" and t["referral_note"] == "Intro via Sam"
    assert t["status"] == "applied" and t["updated_at"] == before_ticket["updated_at"]
    hist = tickets.get_history(conn, tid)
    assert len(hist) == before + 2
    assert [(h["status"], h["actor"], h["reason"]) for h in hist[-2:]] == [
        ("applied", "user", "note"), ("applied", "user", "referral note")]
    tickets.set_note(conn, tid, "")
    assert tickets.get_ticket(conn, tid)["notes"] in ("", None)


def test_set_note_errors(conn):
    from hireember import tickets

    tid = make_ticket(conn, "n2", "pending")
    before = len(tickets.get_history(conn, tid))
    with pytest.raises(tickets.NoteTooLongError) as exc:
        tickets.set_note(conn, tid, "x" * 10001)
    assert str(exc.value) == "Note is too long (max 10,000 characters)."
    assert isinstance(exc.value, tickets.TicketError)
    with pytest.raises(ValueError):
        tickets.set_note(conn, tid, "x", kind="bogus")
    with pytest.raises(tickets.TicketNotFoundError):
        tickets.set_note(conn, 99999, "x")
    assert len(tickets.get_history(conn, tid)) == before


# -- AC-8: answers ----------------------------------------------------------

def test_update_answer(conn):
    from hireember import answers

    aid = answers.save_answer(conn, "Years of Python?", "5", "user")
    answers.update_answer(conn, aid, "How many years of Python do you have?", "6")
    row = next(a for a in answers.list_answers(conn) if a["id"] == aid)
    assert row["question_text"] == "How many years of Python do you have?"
    assert row["answer"] == "6" and row["source"] == "user"
    assert row["normalized_key"] == answers.normalize_question(row["question_text"])


def test_update_answer_errors(conn):
    from hireember import answers

    aid = answers.save_answer(conn, "Favourite colour?", "blue")
    with pytest.raises(answers.AnswerError) as exc:
        answers.update_answer(conn, aid, "Favourite colour?", "  ")
    assert str(exc.value) == "Answer cannot be empty."
    assert isinstance(exc.value, ValueError)
    with pytest.raises(answers.AnswerError) as exc:
        answers.update_answer(conn, 9999, "q", "a")
    assert str(exc.value) == "Answer 9999 not found."
    with pytest.raises(answers.SensitiveQuestionError):
        answers.update_answer(conn, aid, "What is your password?", "hunter2")
    row = answers.list_answers(conn)[0]
    assert row["answer"] == "blue" and row["question_text"] == "Favourite colour?"


def test_delete_answer_leaves_queue_and_tickets(conn):
    from hireember import answers

    tid = make_ticket(conn, "d1", "blocked for human")
    qid = answers.queue_question(conn, tid, "unknown question", "Shoe size?")
    aid = answers.save_answer(conn, "Shoe size?", "42")
    answers.delete_answer(conn, aid)
    assert answers.list_answers(conn) == []
    assert [q["id"] for q in answers.list_queue(conn)] == [qid]
    with pytest.raises(answers.AnswerError):
        answers.delete_answer(conn, aid)


def test_merge_answers(conn):
    from hireember import answers

    k = answers.save_answer(conn, "Work authorization?", "Yes", "user")
    r = answers.save_answer(conn, "Are you authorized to work?", "Yes, citizen", "user",
                            replace=False)
    conn.execute("UPDATE answers SET times_used = 2, last_used_at = '2026-01-01' WHERE id = ?", (k,))
    conn.execute("UPDATE answers SET times_used = 3, last_used_at = '2026-06-01' WHERE id = ?", (r,))
    conn.commit()
    assert answers.merge_answers(conn, k, r, question="Are you authorized to work?",
                                 answer="Yes, citizen") == k
    rows = answers.list_answers(conn)
    assert [x["id"] for x in rows] == [k]
    assert rows[0]["question_text"] == "Are you authorized to work?"
    assert rows[0]["answer"] == "Yes, citizen"
    assert rows[0]["times_used"] == 5 and rows[0]["last_used_at"] == "2026-06-01"


def test_merge_defaults_keep_own_text_and_failures_change_nothing(conn):
    from hireember import answers

    k = answers.save_answer(conn, "Q one?", "A one")
    r = answers.save_answer(conn, "Q two?", "A two", replace=False)
    with pytest.raises(answers.AnswerError):
        answers.merge_answers(conn, k, k)
    with pytest.raises(answers.AnswerError):
        answers.merge_answers(conn, k, 9999)
    with pytest.raises(answers.AnswerError):
        answers.merge_answers(conn, k, r, answer=" ")
    assert len(answers.list_answers(conn)) == 2
    assert answers.list_answers(conn)[0]["answer"] == "A one"
    answers.merge_answers(conn, k, r)
    rows = answers.list_answers(conn)
    assert len(rows) == 1 and rows[0]["answer"] == "A one" and rows[0]["question_text"] == "Q one?"


def test_answers_http_roundtrip(conn, api):
    from hireember import answers

    a = answers.save_answer(conn, "Q a?", "A a")
    b = answers.save_answer(conn, "Q b?", "A b", replace=False)
    c = answers.save_answer(conn, "Q c?", "A c", replace=False)
    status, data = api.get("/api/answers")
    assert status == 200
    assert {x["id"] for x in data["answers"]} == {a, b, c}
    for key in ("id", "question", "answer", "source", "last_used_at", "times_used"):
        assert key in data["answers"][0]

    assert api.json("PUT", f"/api/answers/{a}", {"question": "Q a?", "answer": "new"}) == (
        200, {"ok": True, "message": "Answer saved."})
    status, data = api.json("PUT", f"/api/answers/{a}", {"question": "Q a?", "answer": ""})
    assert status == 400 and data["error"] == "Answer cannot be empty."
    assert api.json("PUT", "/api/answers/9999", {"question": "q", "answer": "a"})[0] == 404
    assert next(x for x in api.get("/api/answers")[1]["answers"] if x["id"] == a)["answer"] == "new"

    status, _ = api.json("POST", "/api/answers/merge", {"keep_id": a, "remove_id": a})
    assert status == 400
    assert api.json("POST", "/api/answers/merge",
                    {"keep_id": a, "remove_id": b, "question": None, "answer": None}) == (
        200, {"ok": True})
    assert {x["id"] for x in api.get("/api/answers")[1]["answers"]} == {a, c}

    assert api.json("DELETE", f"/api/answers/{c}") == (200, {"ok": True})
    assert api.json("DELETE", f"/api/answers/{c}")[0] == 404
    assert [x["id"] for x in api.get("/api/answers")[1]["answers"]] == [a]


# -- AC-8: resumes ----------------------------------------------------------

def test_update_resume_meta(conn, tmp_path):
    from hireember import resumes

    r1 = resumes.add_resume(conn, resume_file(tmp_path, "a.txt"), "Alpha", "Python, Go")
    r2 = resumes.add_resume(conn, resume_file(tmp_path, "b.txt"), "Beta")
    resumes.update_resume_meta(conn, r1, name="Alpha Prime", tags="Rust, rust, Backend")
    row = next(r for r in resumes.list_resumes(conn) if r["id"] == r1)
    assert row["name"] == "Alpha Prime" and row["tags"] == ["rust", "backend"]
    resumes.update_resume_meta(conn, r1, tags="x")
    assert next(r for r in resumes.list_resumes(conn) if r["id"] == r1)["name"] == "Alpha Prime"
    with pytest.raises(resumes.ResumeError) as exc:
        resumes.update_resume_meta(conn, r1, name="  ")
    assert str(exc.value) == "Name cannot be empty."
    with pytest.raises(resumes.ResumeError) as exc:
        resumes.update_resume_meta(conn, r1, name="beta")
    assert str(exc.value) == 'A resume named "beta" already exists.'
    resumes.update_resume_meta(conn, r2, name="BETA")


def test_resumes_http_edit_and_replace_file(conn, api, tmp_path):
    from hireember import resumes

    rid = resumes.add_resume(conn, resume_file(tmp_path, "orig.txt", "old text"), "Main", "py")
    status, data = api.get("/api/resumes")
    assert status == 200
    row = data["resumes"][0]
    assert row["id"] == rid and row["name"] == "Main" and row["tags"] == ["py"]
    assert row["pinned"] is False and isinstance(row["file_name"], str) and row["file_name"]

    assert api.json("PUT", f"/api/resumes/{rid}", {"name": "Main 2", "tags": "a, b"}) == (
        200, {"ok": True, "message": "Resume saved."})
    status, data = api.json("PUT", f"/api/resumes/{rid}", {"name": " ", "tags": ""})
    assert status == 400 and data["error"] == "Name cannot be empty."
    row = api.get("/api/resumes")[1]["resumes"][0]
    assert row["name"] == "Main 2" and row["tags"] == ["a", "b"]

    status, _, body = api.request("POST", f"/api/resumes/{rid}/file", raw=b"new text body",
                                  headers={"X-Filename": "new.txt"})
    assert status == 200
    import json
    payload = json.loads(body)
    assert payload["ok"] is True and payload["message"] == "Resume file replaced."
    path = resumes.list_resumes(conn)[0]["file_path"]
    assert open(path, encoding="utf-8").read() == "new text body"

    status, _, body = api.request("POST", f"/api/resumes/{rid}/file", raw=b"x",
                                  headers={"X-Filename": "bad.doc"})
    assert status == 400
    assert json.loads(body)["error"] == "Unsupported format. Provide a .pdf, .txt or .docx file."
    assert open(resumes.list_resumes(conn)[0]["file_path"], encoding="utf-8").read() == "new text body"
