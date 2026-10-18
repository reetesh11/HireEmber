"""Ten-group profile step with a scripted ask."""

import io

import pytest
from rich.console import Console

from hireember.database import close_connection, init_db
from hireember.profile import PROFILE_GROUPS, group_answers
from hireember.wizard.init import run_profile_step

ALL = [q for g in PROFILE_GROUPS for q in g.questions]


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    from hireember import config
    config.ensure_dirs()
    yield c
    close_connection(db)


def _console():
    return Console(file=io.StringIO(), width=200)


def _ask(log, blank_once=None):
    seen = set()

    def ask(question, **kwargs):
        log.append(question)
        if question == blank_once and question not in seen:
            seen.add(question)
            return "  "
        if question not in ALL:
            return "y"
        return "skip" if question in PROFILE_GROUPS[-1].questions else "a, b"
    return ask


def test_blank_reasks_and_skip_is_stored(conn):
    log = []
    profile = run_profile_step(conn, _ask(log, blank_once=ALL[0]), console=_console())
    assert log.count(ALL[0]) == 2
    assert all(r["answer"] == "skip" for r in group_answers(conn, "eeo"))
    assert profile["skills_boundary"]["languages"] == ["a", "b"]
    assert profile["eeo_voluntary"]["gender"] == "Decline to self-identify"
    assert "password" not in str(profile).lower()


def test_rerun_keeps_stored_groups(conn):
    run_profile_step(conn, _ask([]), console=_console())
    log = []
    run_profile_step(conn, _ask(log), console=_console())
    assert not [q for q in log if q in ALL]
