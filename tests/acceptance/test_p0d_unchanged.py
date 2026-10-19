"""Phase 0d unchanged behaviour (AC-12) and doctor states: passes before and after."""

import json
import re

import pytest
from typer.testing import CliRunner

from p0d_helpers import FULL_LINES, console, isolate, output

POSTAL = "What is your postal or ZIP code?"


@pytest.fixture
def env(monkeypatch, tmp_path):
    return isolate(monkeypatch, tmp_path)


def _questions():
    from hireember.profile import PROFILE_GROUPS

    return [q for g in PROFILE_GROUPS for q in g.questions]


def _not_resume_answerable():
    from hireember.profile import PROFILE_GROUPS

    return [q for g in PROFILE_GROUPS if g.key not in ("contact", "location") for q in g.questions] + [POSTAL]


def test_profile_without_resume_asks_every_question_plainly_in_order(env):
    from hireember.wizard.init import run_profile_step

    conn, data, src = env
    calls = []

    def ask(question, **kwargs):
        calls.append((question, kwargs))
        return "skip" if "EEO" in question else f"answer to {question}"

    run_profile_step(conn, ask, console=console())
    assert [q for q, _ in calls] == _questions()
    assert all(kw == {} for _, kw in calls)
    saved = json.loads((data / "profile.json").read_text(encoding="utf-8"))
    assert saved["personal"]["email"] == "answer to What is your email address?"


def test_resume_never_changes_questions_it_cannot_answer(env):
    from hireember.wizard.init import run_profile_step

    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n"
                                     + "Postal code M5V 2T6\nAuthorized to work. Salary 90000\n", encoding="utf-8")
    calls = []

    def ask(question, **kwargs):
        calls.append((question, kwargs))
        return kwargs.get("default") or ("skip" if "EEO" in question else f"answer to {question}")

    run_profile_step(conn, ask, console=console())
    assert [q for q, _ in calls] == _questions()
    for question, kwargs in calls:
        if question in _not_resume_answerable():
            assert kwargs == {}, question


def test_blank_reply_is_reasked_as_before(env):
    from hireember.wizard.init import run_profile_step

    conn, data, src = env
    seen = {"blank": False}

    def ask(question, **kwargs):
        if question == "What is your earliest start date?" and not seen["blank"]:
            seen["blank"] = True
            return " "
        return "skip" if "EEO" in question else f"answer to {question}"

    c = console()
    run_profile_step(conn, ask, console=c)
    assert "An answer is needed here." in output(c)


def _doctor():
    from hireember.cli import app

    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    return result.output


def test_doctor_only_pdf_found_is_unchanged(env):
    conn, data, src = env
    (data / "resume.pdf").write_bytes(b"%PDF-1.4")
    out = _doctor()
    assert "Only PDF found" in out
    assert re.search(r"^\s+resume\.txt\s+WARN\b", out, re.M)


def test_doctor_resume_missing_is_unchanged(env):
    conn, data, src = env
    out = _doctor()
    assert re.search(r"^\s+resume\.txt\s+MISSING\b", out, re.M)
    assert "Only PDF found" not in out


def test_doctor_resume_txt_present_is_ok(env):
    conn, data, src = env
    (data / "resume.txt").write_text("hello", encoding="utf-8")
    (data / "resume.pdf").write_bytes(b"%PDF-1.4")
    out = _doctor()
    assert re.search(r"^\s+resume\.txt\s+OK\b", out, re.M)
    assert "Only PDF found" not in out
