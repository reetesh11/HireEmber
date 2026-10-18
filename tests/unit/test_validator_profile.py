import copy

from hireember.scoring.validator import validate_against_profile

PROFILE = {
    "skills_boundary": {"languages": ["Python", "SQL"], "tools": ["Git"]},
    "resume_facts": {
        "preserved_companies": ["Company A"],
        "preserved_projects": ["Project X"],
        "preserved_school": "Your University",
        "real_metrics": ["50% improvement", "10x faster"],
    },
}
DATA = {
    "skills": {"Languages": "Python, sql", "Tools": "Git"},
    "experience": [{"header": "company a | Berlin", "bullets": ["Got a 50% improvement, 10x faster."]}],
    "projects": [{"header": "Project X - side", "bullets": ["Built it."]}],
    "education": "Your University | BSc",
}


def _with(**changes):
    data = copy.deepcopy(DATA)
    data.update(changes)
    return data


def test_valid():
    assert validate_against_profile(DATA, PROFILE) == []


def test_each_reason():
    bad_job = [{"header": "Acme | X", "bullets": ["Saved 3M and 95% of time."]}]
    assert validate_against_profile(_with(experience=bad_job), PROFILE) == [
        'employer "Acme" not in resume facts',
        'metric "3M" not in resume facts',
        'metric "95%" not in resume facts',
    ]
    assert validate_against_profile(_with(projects=[{"header": "Z", "bullets": []}]), PROFILE) == [
        'project "Z" not in resume facts']
    assert validate_against_profile(_with(education="Other College | BA"), PROFILE) == [
        'school "Other College" not in resume facts']
    assert validate_against_profile(_with(skills={"Tools": "Git, Rust"}), PROFILE) == [
        'skill "Rust" not in skills boundary']
