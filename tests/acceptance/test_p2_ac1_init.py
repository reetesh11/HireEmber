"""Phase 2 AC-1: init asks all ten profile groups and stores an answer for each."""

import io
import json

import pytest
from rich.console import Console

from hireember.database import close_connection, init_db

from p2_helpers import REPO_ROOT  # noqa: F401

KEYS = ["contact", "location", "work_authorization", "availability", "compensation",
        "experience_level", "target_roles", "skills_boundary", "resume_facts", "eeo"]
TITLES = ["Name and contact", "Location", "Work authorization", "Availability",
          "Compensation expectation", "Experience level", "Target roles", "Skills boundary",
          "Resume facts", "EEO preferences"]


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    from hireember import config
    config.ensure_dirs()
    yield c
    close_connection(db)


def _all_questions():
    from hireember.profile import PROFILE_GROUPS
    return [q for g in PROFILE_GROUPS for q in g.questions]


def _scripted(log, blank_first=None):
    seen = set()

    def ask(question, *args, **kwargs):
        log.append(question)
        if blank_first and question == blank_first and question not in seen:
            seen.add(question)
            return "   "
        if question not in _all_questions():
            return "y"  # keep/change prompt
        from hireember.profile import PROFILE_GROUPS
        eeo = next(g for g in PROFILE_GROUPS if g.key == "eeo")
        return "skip" if question in eeo.questions else f"answer to {question}"

    return ask


def _console():
    return Console(file=io.StringIO(), width=200)


def test_ten_groups_in_order():
    from hireember.profile import PROFILE_GROUPS

    assert [g.key for g in PROFILE_GROUPS] == KEYS
    assert [g.title for g in PROFILE_GROUPS] == TITLES
    assert all(g.questions for g in PROFILE_GROUPS)
    assert [g.key for g in PROFILE_GROUPS if g.optional] == ["eeo"]


def test_init_asks_every_group_and_stores_profile_answers(conn):
    from hireember.profile import PROFILE_GROUPS, group_answers
    from hireember.wizard.init import run_profile_step

    log, out = [], _console()
    run_profile_step(conn, _scripted(log), console=out)
    assert log == _all_questions()
    text = out.file.getvalue()
    for n, title in enumerate(TITLES, 1):
        assert f"Profile step {n} of 10: {title}" in text
    for g in PROFILE_GROUPS:
        rows = group_answers(conn, g.key)
        assert rows, f"no stored answer for group {g.key}"
        assert all(r["source"] == "profile" and r["answer"].strip() for r in rows)
        assert len(rows) == len(g.questions)


def test_blank_reply_reasks_and_is_never_stored(conn):
    from hireember.answers import list_answers
    from hireember.wizard.init import run_profile_step

    first = _all_questions()[0]
    log = []
    run_profile_step(conn, _scripted(log, blank_first=first), console=_console())
    assert log.count(first) == 2
    assert all(a["answer"].strip() for a in list_answers(conn))
    assert len(list_answers(conn)) == len(_all_questions())


def test_eeo_skip_is_stored_as_an_answer(conn):
    from hireember.profile import group_answers
    from hireember.wizard.init import run_profile_step

    run_profile_step(conn, _scripted([]), console=_console())
    rows = group_answers(conn, "eeo")
    assert rows and all(r["answer"].strip().lower() == "skip" for r in rows)


def test_returns_and_writes_profile_without_password(conn):
    from hireember import config
    from hireember.profile import contains_key
    from hireember.wizard.init import run_profile_step

    result = run_profile_step(conn, _scripted([]), console=_console())
    assert isinstance(result, dict) and result
    written = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(result))
    assert not contains_key(result, "password")


def test_questions_never_ask_for_sensitive_data():
    from hireember.answers import is_sensitive

    for q in _all_questions():
        assert not is_sensitive(q), q
        assert "password" not in q.lower()


def test_rerun_keeps_stored_groups_unless_changed(conn):
    from hireember.profile import PROFILE_GROUPS
    from hireember.wizard.init import run_profile_step

    run_profile_step(conn, _scripted([]), console=_console())

    log = []
    run_profile_step(conn, _scripted(log), console=_console())
    assert not [q for q in log if q in _all_questions()], "stored groups were re-asked"
    assert any("Keep your Location answers" in q for q in log)

    location = next(g for g in PROFILE_GROUPS if g.key == "location")
    log2 = []

    def ask(question, *args, **kwargs):
        log2.append(question)
        if "Keep your Location answers" in question:
            return "n"
        if question not in _all_questions():
            return "y"
        return "new answer"

    run_profile_step(conn, ask, console=_console())
    asked = [q for q in log2 if q in _all_questions()]
    assert asked == list(location.questions)
