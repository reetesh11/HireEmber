"""Phase 0d init step 2: profile defaults from resume.txt (AC-6, AC-7, AC-8, AC-9)."""

import json
import re

import pytest

from p0d_helpers import (
    BODY, COUNTRY, CITY, EMAIL, FULL_LINES, LINKEDIN, NAME, PHONE, PROVINCE, Q_CONFIRM, Q_PATH,
    Script, console, isolate, output, write_pdf,
)

Q_NAME = "What is your full name?"
Q_EMAIL = "What is your email address?"
Q_PHONE = "What is your phone number?"
Q_LINKEDIN = "What is your LinkedIn URL?"
Q_CITY = "Which city do you live in?"
Q_PROV = "Which province or state do you live in?"
Q_COUNTRY = "Which country do you live in?"
Q_POSTAL = "What is your postal or ZIP code?"
CONTACT = [Q_NAME, Q_EMAIL, Q_PHONE, Q_LINKEDIN]
LOCATION = [Q_CITY, Q_PROV, Q_COUNTRY, Q_POSTAL]
EXPECTED = {Q_NAME: NAME, Q_EMAIL: EMAIL, Q_PHONE: PHONE, Q_LINKEDIN: LINKEDIN,
            Q_CITY: CITY, Q_PROV: PROVINCE, Q_COUNTRY: COUNTRY}
KEEP_CONTACT = "Keep your Name and contact answers? [Y/n]"
KEEP_LOCATION = "Keep your Location answers? [Y/n]"


@pytest.fixture
def env(monkeypatch, tmp_path):
    return isolate(monkeypatch, tmp_path)


def all_questions():
    from hireember.profile import PROFILE_GROUPS

    return [q for g in PROFILE_GROUPS for q in g.questions]


class EnterAsk:
    """Presses Enter when a default is offered; otherwise answers 'typed: <question>'."""

    def __init__(self, keep="y", overrides=None):
        self.keep, self.overrides = keep, overrides or {}
        self.defaults: dict[str, str | None] = {}
        self.log: list[str] = []
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, question, **kwargs):
        self.log.append(question)
        self.calls.append((question, kwargs))
        if question.startswith("Keep your"):
            return self.keep
        default = kwargs.get("default")
        self.defaults[question] = default
        if question in self.overrides:
            return self.overrides[question]
        if default is not None:
            return default
        return "skip" if "EEO" in question or "gender" in question.lower() else f"typed: {question}"


def run_profile(conn, ask):
    from hireember.wizard.init import run_profile_step

    c = console()
    profile = run_profile_step(conn, ask, console=c)
    return profile, output(c)


def stored(conn):
    from hireember.answers import list_answers

    return {r["question_text"]: r["answer"] for r in list_answers(conn) if r["source"] == "profile"}


def test_known_values_are_offered_as_defaults_and_stored_on_enter(env):
    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n", encoding="utf-8")
    ask = EnterAsk()
    profile, _ = run_profile(conn, ask)
    for question, value in EXPECTED.items():
        assert ask.defaults[question] == value, question
    assert ask.defaults[Q_POSTAL] is None
    bank = stored(conn)
    for question, value in EXPECTED.items():
        assert bank[question] == value
    personal = json.loads((data / "profile.json").read_text(encoding="utf-8"))["personal"]
    assert personal["full_name"] == NAME and personal["email"] == EMAIL
    assert personal["phone"] == PHONE and personal["linkedin_url"] == LINKEDIN
    assert (personal["city"], personal["province_state"], personal["country"]) == (CITY, PROVINCE, COUNTRY)
    assert profile["personal"]["email"] == EMAIL


def test_typing_replaces_a_default(env):
    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n", encoding="utf-8")
    ask = EnterAsk(overrides={Q_EMAIL: "other@example.org"})
    run_profile(conn, ask)
    assert ask.defaults[Q_EMAIL] == EMAIL
    assert stored(conn)[Q_EMAIL] == "other@example.org"


def test_missing_fields_are_asked_without_default_and_nothing_invented(env):
    conn, data, src = env
    (data / "resume.txt").write_text(f"{NAME}\n{EMAIL}\n" + "\n".join(BODY) + "\n", encoding="utf-8")
    ask = EnterAsk()
    run_profile(conn, ask)
    assert ask.defaults[Q_NAME] == NAME and ask.defaults[Q_EMAIL] == EMAIL
    for question in (Q_PHONE, Q_LINKEDIN, Q_CITY, Q_PROV, Q_COUNTRY, Q_POSTAL):
        assert ask.defaults[question] is None, question
        # asked exactly as today: no keyword arguments at all
        assert [kw for q, kw in ask.calls if q == question] == [{}]
    bank = stored(conn)
    assert bank[Q_PHONE] == f"typed: {Q_PHONE}"
    assert bank[Q_CITY] == f"typed: {Q_CITY}"


def test_resume_with_bad_bytes_does_not_crash(env):
    conn, data, src = env
    (data / "resume.txt").write_bytes(b"\xff\xfe\x00 bad bytes \x80\x81\n" + EMAIL.encode() + b"\n")
    ask = EnterAsk()
    run_profile(conn, ask)
    assert ask.defaults[Q_EMAIL] == EMAIL


# -- stored answers win (AC-8) ------------------------------------------------------------------


def test_partly_stored_group_proposes_only_for_unstored_questions(env):
    from hireember import answers

    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n", encoding="utf-8")
    answers.save_answer(conn, Q_NAME, "Stored Name", source="profile")
    ask = EnterAsk()
    run_profile(conn, ask)
    assert ask.defaults[Q_NAME] is None
    assert ask.defaults[Q_EMAIL] == EMAIL
    assert stored(conn)[Q_NAME] == f"typed: {Q_NAME}"  # asked as today; the stored value got no resume default


# -- doctor after PDF + accepted defaults (AC-9) --------------------------------------------------


def test_doctor_shows_resume_ok_after_pdf_flow(env):
    from typer.testing import CliRunner

    from hireember.cli import app
    from hireember.wizard.init import run_resume_step

    conn, data, src = env
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    run_resume_step(conn, Script({Q_PATH: [str(pdf)], Q_CONFIRM: ["y"]}), console=console())
    ask = EnterAsk()
    run_profile(conn, ask)
    for question, value in EXPECTED.items():
        assert ask.defaults[question] == value, question  # PDF-extracted text feeds the proposals
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert re.search(r"^\s+resume\.txt\s+OK\b", result.output, re.M), result.output
    assert "Only PDF found" not in result.output
