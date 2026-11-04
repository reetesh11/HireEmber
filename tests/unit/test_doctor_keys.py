from hireember.doctor import Check, check_search_config_keys


def test_suggestion_and_no_suggestion():
    [c] = check_search_config_keys({"title_include": ["a"], "exclude_title": ["b"]})
    assert c.note.endswith("Did you mean 'title_exclude'?")
    [c] = check_search_config_keys({"title_include": ["a"], "zzzzqq": 1})
    assert "Did you mean" not in c.note


def test_empty_lists_warning_and_clean():
    assert len(check_search_config_keys({"queries": [{"query": "x"}]})) == 1
    assert check_search_config_keys({"queries": [{"query": "x"}], "exclude_titles": ["s"]}) == []
    assert isinstance(Check("a", "WARN", "b"), Check)
