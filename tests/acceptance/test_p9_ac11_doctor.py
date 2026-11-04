"""Phase 9 AC-11: doctor warns on unknown config keys and on a query list with both title lists empty."""

from hireember.doctor import Check


def check_search_config_keys(*args):
    from hireember.doctor import check_search_config_keys as fn

    return fn(*args)


EMPTY_MSG = ("Job-board queries are set but title_include and title_exclude are both empty; "
             "discovery will keep every title.")


def test_misspelt_key_warns_with_suggestion():
    cfg = {"queries": [{"query": "x"}], "title_include": ["engineer"], "exclude_title": ["sales"]}
    assert check_search_config_keys(cfg) == [Check(
        "searches.yaml", "WARN",
        "Unknown config key 'exclude_title' in searches.yaml (not read by any code). "
        "Did you mean 'title_exclude'?")]


def test_unknown_key_without_close_match_has_no_suggestion():
    cfg = {"title_include": ["engineer"], "zzzzqq": 1}
    [check] = check_search_config_keys(cfg)
    assert check.status == "WARN"
    assert check.note == "Unknown config key 'zzzzqq' in searches.yaml (not read by any code)."


def test_queries_with_both_lists_empty_warns():
    assert check_search_config_keys({"queries": [{"query": "x"}]}) == [Check("searches.yaml", "WARN", EMPTY_MSG)]
    assert check_search_config_keys({"queries": [{"query": "x"}], "title_include": []}) == [
        Check("searches.yaml", "WARN", EMPTY_MSG)]


def test_clean_configs_return_nothing():
    assert check_search_config_keys({"queries": [{"query": "x"}], "title_include": ["engineer"]}) == []
    assert check_search_config_keys({"queries": [{"query": "x"}], "exclude_titles": ["sales"]}) == []
    assert check_search_config_keys({"defaults": {}, "locations": []}) == []


def test_missing_file_gives_nothing_and_file_is_read(tmp_path, monkeypatch):
    from p9_helpers import use_config

    use_config(tmp_path, monkeypatch)
    assert check_search_config_keys() == []
    use_config(tmp_path, monkeypatch, searches={"queries": [{"query": "x"}], "exclude_title": ["a"]})
    notes = [c.note for c in check_search_config_keys()]
    assert any("Unknown config key 'exclude_title'" in n for n in notes)
