from hireember import search_config as sc


def test_title_alias_precedence():
    assert sc.title_lists({"exclude_titles": ["a"]}) == ([], ["a"])
    assert sc.title_lists({"title_exclude": [], "exclude_titles": ["a"]}) == ([], [])
    assert sc.title_lists({"title_include": ["x", 3]}) == (["x"], [])


def test_location_lists_new_block_wins():
    old = {"location_accept": ["A"], "location_reject_non_remote": ["B"]}
    assert sc.location_lists(old) == (["A"], ["B"])
    both = {**old, "location": {"accept_patterns": ["C"]}}
    assert sc.location_lists(both) == (["C"], ["B"])


def test_load_missing(tmp_path, monkeypatch):
    from hireember import config
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", tmp_path / "none.yaml")
    assert sc.load() == {}
