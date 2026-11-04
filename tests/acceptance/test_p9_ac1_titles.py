"""Phase 9 AC-1 (and the title half of AC-7): hireember.titles.title_filter and propose_title_lists."""

import pytest


def title_filter(*args):
    from hireember.titles import title_filter as fn

    return fn(*args)


def propose_title_lists(*args):
    from hireember.titles import propose_title_lists as fn

    return fn(*args)



def test_exclude_drops_program_manager_keeps_backend_engineer():
    exclude = ["sales", "program manager"]
    assert title_filter("Senior Program Manager", [], exclude) == "title: program manager"
    assert title_filter("Backend Engineer", [], exclude) is None


def test_include_drops_non_matching_title():
    assert title_filter("Account Executive", ["engineer"], []) == "title: not in target roles"
    assert title_filter("Backend Engineer", ["engineer"], []) is None


def test_whole_word_not_substring():
    assert title_filter("Sales Engineer", [], ["sales"]) == "title: sales"
    assert title_filter("Salesforce Developer", [], ["sales"]) is None
    assert title_filter("Sales/Marketing Lead", [], ["sales"]) == "title: sales"


def test_phrase_and_boundary_runs():
    assert title_filter("Senior  Program   Manager", [], ["program manager"]) == "title: program manager"
    assert title_filter("Program Director", [], ["program manager"]) is None
    assert title_filter("TS-SCI Engineer", [], ["TS/SCI"]) == "title: TS/SCI"


def test_case_insensitive_and_reason_uses_entry_as_written():
    assert title_filter("SENIOR PROGRAM MANAGER", [], ["  Program Manager "]) == "title: Program Manager"
    assert title_filter("software ENGINEER", ["Engineer"], []) is None


def test_exclude_checked_before_include():
    assert title_filter("Sales Engineer", ["engineer"], ["sales"]) == "title: sales"


def test_empty_lists_keep_everything_and_unusable_entries_ignored():
    assert title_filter("Anything At All", [], []) is None
    assert title_filter("Anything At All", None, None) is None
    assert title_filter("Anything", ["", "  ", 5, None], [None, 3, " "]) is None


def test_empty_title_with_include_is_dropped_without_include_kept():
    assert title_filter(None, ["engineer"], []) == "title: not in target roles"
    assert title_filter("", ["engineer"], []) == "title: not in target roles"
    assert title_filter(None, [], ["sales"]) is None


def test_propose_lists_for_software_input():
    include, exclude = propose_title_lists(["Backend Engineer", "Backend Engineer"], "Software Engineer",
                                           "I write code")
    assert include == [i.lower() for i in include] and len(include) == len(set(include))
    assert {"backend engineer", "software engineer", "engineer", "developer"} <= set(include)
    for term in ("sales", "program manager", "account executive", "recruiter", "marketing",
                 "customer success", "business development"):
        assert term in exclude
    assert exclude == [e.lower() for e in exclude] and len(exclude) == len(set(exclude))


def test_propose_lists_non_software_has_no_exclude():
    include, exclude = propose_title_lists(["Nurse"], "Registered Nurse", "Ward care")
    assert "nurse" in include and "engineer" not in include
    assert exclude == []


@pytest.mark.parametrize("resume", ["Experienced software developer", ""])
def test_software_detected_from_resume_text(resume):
    include, exclude = propose_title_lists([], "", resume)
    assert bool(exclude) == bool(resume)
