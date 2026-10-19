"""Phase 0d profile step: no proposals when none are confident or answers are stored (AC-7, AC-8); green before and after."""

import json

import pytest

from p0d_helpers import (
    COUNTRY, CITY, EMAIL, FULL_LINES, LINKEDIN, NAME, PHONE, PROVINCE, console, isolate, output,
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


def _store_all(conn):
    from hireember import answers

    for question in CONTACT + LOCATION:
        answers.save_answer(conn, question, f"Stored {question}", source="profile")


def test_no_default_means_blank_reply_is_reasked(env):
    conn, data, src = env
    (data / "resume.txt").write_text(f"{NAME}\n", encoding="utf-8")
    replies = {Q_EMAIL: ["", "  ", "me@example.com"]}

    def ask(question, **kwargs):
        if question in replies:
            return replies[question].pop(0)
        return kwargs.get("default") or f"typed: {question}"

    _, out = run_profile(conn, ask)
    assert out.count("An answer is needed here.") == 2
    assert stored(conn)[Q_EMAIL] == "me@example.com"


def test_ambiguous_resume_values_give_no_defaults(env):
    conn, data, src = env
    (data / "resume.txt").write_text(
        f"{NAME}\nToronto, Ontario\na@example.com | b@example.org | 416-555-0142 | 647-555-0199\n",
        encoding="utf-8")
    ask = EnterAsk()
    run_profile(conn, ask)
    for question in (Q_EMAIL, Q_PHONE, Q_CITY, Q_PROV, Q_COUNTRY):
        assert ask.defaults[question] is None, question


def test_no_resume_txt_gives_no_defaults_and_no_crash(env):
    conn, data, src = env
    ask = EnterAsk()
    run_profile(conn, ask)
    assert all(ask.defaults[q] is None for q in all_questions() if not q.startswith("Keep"))


def test_complete_groups_are_kept_and_not_replaced_by_resume_values(env):
    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n", encoding="utf-8")
    _store_all(conn)
    ask = EnterAsk(keep="y")
    run_profile(conn, ask)
    assert KEEP_CONTACT in ask.log and KEEP_LOCATION in ask.log
    assert not set(CONTACT + LOCATION) & set(ask.log)
    bank = stored(conn)
    for question in CONTACT + LOCATION:
        assert bank[question] == f"Stored {question}"


def test_declining_keep_gives_no_proposal_for_stored_questions(env):
    conn, data, src = env
    (data / "resume.txt").write_text("\n".join(FULL_LINES) + "\n", encoding="utf-8")
    _store_all(conn)
    ask = EnterAsk(keep="n")
    run_profile(conn, ask)
    for question in CONTACT + LOCATION:
        assert ask.defaults[question] is None, question
        assert stored(conn)[question] == f"typed: {question}"
    assert NAME not in json.dumps(stored(conn))


