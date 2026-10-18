"""Profile groups: the ten sets of questions asked by ``hireember init``.

Answers live in the answer bank (source ``profile``); ``profile.json`` is built from them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from hireember.tickets import normalize_text


@dataclass(frozen=True)
class ProfileGroup:
    key: str
    title: str
    questions: tuple[str, ...]
    optional: bool = False


PROFILE_GROUPS: tuple[ProfileGroup, ...] = (
    ProfileGroup("contact", "Name and contact", (
        "What is your full name?",
        "What is your email address?",
        "What is your phone number?",
        "What is your LinkedIn URL?",
    )),
    ProfileGroup("location", "Location", (
        "Which city do you live in?",
        "Which province or state do you live in?",
        "Which country do you live in?",
        "What is your postal or ZIP code?",
    )),
    ProfileGroup("work_authorization", "Work authorization", (
        "Are you legally authorized to work in your target country?",
        "Will you now or in the future need visa sponsorship?",
    )),
    ProfileGroup("availability", "Availability", (
        "What is your earliest start date?",
    )),
    ProfileGroup("compensation", "Compensation expectation", (
        "What is your expected annual salary?",
        "Which currency is that salary in?",
    )),
    ProfileGroup("experience_level", "Experience level", (
        "How many years of professional experience do you have?",
        "What is your highest education level?",
    )),
    ProfileGroup("target_roles", "Target roles", (
        "Which role are you applying for?",
    )),
    ProfileGroup("skills_boundary", "Skills boundary", (
        "Which programming languages do you know? (comma-separated)",
        "Which frameworks and libraries do you know? (comma-separated)",
        "Which tools and platforms do you know? (comma-separated)",
    )),
    ProfileGroup("resume_facts", "Resume facts", (
        "Which companies must always stay on your resume? (comma-separated)",
        "Which projects must always stay on your resume? (comma-separated)",
        "Which school must stay on your resume?",
        "Which real metrics may be used on your resume? (comma-separated)",
    )),
    ProfileGroup("eeo", "EEO preferences", (
        "What is your gender (voluntary)?",
        "What is your race or ethnicity (voluntary)?",
        "What is your veteran status (voluntary)?",
        "What is your disability status (voluntary)?",
    ), optional=True),
)

# Where each question lands in profile.json: (section, field, kind), parallel to the questions.
_FIELDS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "contact": (("personal", "full_name", "text"), ("personal", "email", "text"),
                ("personal", "phone", "text"), ("personal", "linkedin_url", "text")),
    "location": (("personal", "city", "text"), ("personal", "province_state", "text"),
                 ("personal", "country", "text"), ("personal", "postal_code", "text")),
    "work_authorization": (("work_authorization", "legally_authorized_to_work", "text"),
                           ("work_authorization", "require_sponsorship", "text")),
    "availability": (("availability", "earliest_start_date", "text"),),
    "compensation": (("compensation", "salary_expectation", "text"),
                     ("compensation", "salary_currency", "text")),
    "experience_level": (("experience", "years_of_experience_total", "text"),
                         ("experience", "education_level", "text")),
    "target_roles": (("experience", "target_role", "text"),),
    "skills_boundary": (("skills_boundary", "languages", "list"),
                        ("skills_boundary", "frameworks", "list"),
                        ("skills_boundary", "tools", "list")),
    "resume_facts": (("resume_facts", "preserved_companies", "list"),
                     ("resume_facts", "preserved_projects", "list"),
                     ("resume_facts", "preserved_school", "text"),
                     ("resume_facts", "real_metrics", "list")),
    "eeo": (("eeo_voluntary", "gender", "text"), ("eeo_voluntary", "race_ethnicity", "text"),
            ("eeo_voluntary", "veteran_status", "text"), ("eeo_voluntary", "disability_status", "text")),
}

_STR = {"type": "string"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}


def _section(**fields: dict) -> dict:
    return {"type": "object", "properties": fields}


PROFILE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "personal": _section(full_name=_STR, email=_STR, phone=_STR, linkedin_url=_STR, city=_STR,
                             province_state=_STR, country=_STR, postal_code=_STR),
        "work_authorization": _section(legally_authorized_to_work=_STR, require_sponsorship=_STR),
        "availability": _section(earliest_start_date=_STR),
        "compensation": _section(salary_expectation=_STR, salary_currency=_STR,
                                 salary_range_min=_STR, salary_range_max=_STR),
        "experience": _section(years_of_experience_total=_STR, education_level=_STR, target_role=_STR),
        "skills_boundary": _section(languages=_STR_LIST, frameworks=_STR_LIST, tools=_STR_LIST),
        "resume_facts": _section(preserved_companies=_STR_LIST, preserved_projects=_STR_LIST,
                                 preserved_school=_STR, real_metrics=_STR_LIST),
        "eeo_voluntary": _section(gender=_STR, race_ethnicity=_STR, veteran_status=_STR,
                                  disability_status=_STR),
    },
}


def contains_key(obj, name: str) -> bool:
    """Case-insensitive recursive search for a dict key in dicts and lists."""
    target = name.lower()
    if isinstance(obj, dict):
        return any(str(k).lower() == target or contains_key(v, name) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(contains_key(v, name) for v in obj)
    return False


def _stored(conn: sqlite3.Connection) -> dict[str, str]:
    """Profile-source answers by normalized key (lowest id wins)."""
    rows = conn.execute("SELECT normalized_key, answer FROM answers WHERE source = 'profile' "
                        "ORDER BY id DESC").fetchall()
    return {r[0]: r[1] for r in rows}


def group_answers(conn: sqlite3.Connection, group_key: str) -> list[dict]:
    """Stored profile answers whose key matches one of the group's questions."""
    group = next(g for g in PROFILE_GROUPS if g.key == group_key)
    keys = {normalize_text(q) for q in group.questions}
    rows = conn.execute(
        "SELECT question_text, normalized_key, answer, source, times_used, last_used_at "
        "FROM answers WHERE source = 'profile' ORDER BY id").fetchall()
    return [dict(zip(r.keys(), tuple(r))) for r in rows if r["normalized_key"] in keys]


def group_complete(conn: sqlite3.Connection, group: ProfileGroup) -> bool:
    stored = _stored(conn)
    return all(normalize_text(q) in stored for q in group.questions)


def build_profile(conn: sqlite3.Connection) -> dict:
    """Build the profile.json layout from the stored profile answers."""
    stored = _stored(conn)
    profile: dict = {}
    for group in PROFILE_GROUPS:
        for question, (section, field, kind) in zip(group.questions, _FIELDS[group.key]):
            value = stored.get(normalize_text(question))
            if value is None:
                continue
            value = value.strip()
            if group.optional and value.lower() in ("skip", "decline", "decline to answer"):
                value = "Decline to self-identify"
            if kind == "list":
                value = [s.strip() for s in value.split(",") if s.strip()]
            profile.setdefault(section, {})[field] = value
    comp = profile.get("compensation", {})
    if "salary_expectation" in comp:
        comp.setdefault("salary_range_min", comp["salary_expectation"])
        comp.setdefault("salary_range_max", comp["salary_expectation"])
    return profile
