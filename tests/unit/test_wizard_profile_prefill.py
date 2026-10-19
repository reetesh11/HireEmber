from hireember import answers, config
from hireember.database import init_db
from hireember.wizard.init import run_profile_step

Q_EMAIL = "What is your email address?"
Q_POSTAL = "What is your postal or ZIP code?"


def _setup(monkeypatch, tmp_path, text):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "RESUME_PATH", data / "resume.txt")
    monkeypatch.setattr("hireember.wizard.init.PROFILE_PATH", data / "profile.json")
    if text is not None:
        (data / "resume.txt").write_text(text, encoding="utf-8")
    return init_db(tmp_path / "t.db")


def _run(conn):
    seen = {}

    def ask(question, **kwargs):
        if question.startswith("Keep"):
            return "y"
        seen[question] = kwargs.get("default")
        return kwargs.get("default") or "x"

    run_profile_step(conn, ask)
    return seen


def test_default_offered_and_stored(monkeypatch, tmp_path):
    conn = _setup(monkeypatch, tmp_path, "Jane Doe\njane@example.com\n")
    seen = _run(conn)
    assert seen[Q_EMAIL] == "jane@example.com"
    assert seen[Q_POSTAL] is None
    assert answers.list_answers(conn)


def test_stored_answer_gets_no_default(monkeypatch, tmp_path):
    conn = _setup(monkeypatch, tmp_path, "Jane Doe\njane@example.com\n")
    answers.save_answer(conn, Q_EMAIL, "old@example.com", source="profile")
    assert _run(conn)[Q_EMAIL] is None
