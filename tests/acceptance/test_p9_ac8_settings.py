"""Phase 9 AC-8: Profile API and search_config read/write the canonical keys in their own files."""

import json

import pytest
import yaml

from p9_helpers import Client, start_server, stop_server, use_config

SEARCHES = {
    "defaults": {"location": "Berlin", "hours_old": 72},
    "locations": [{"location": "Berlin", "remote": False}],
    "queries": [{"query": "Engineer", "tier": 1}],
    "title_include": ["engineer"],
    "exclude_titles": ["sales"],
    "location_accept": ["Berlin"],
    "location_reject_non_remote": ["Paris"],
    "proxy": "http://p:1",
}
PROFILE = {"personal": {"city": "Berlin", "province_state": "BE", "country": "Germany", "full_name": "Jane"},
           "experience": {"target_role": "Engineer"}}


@pytest.fixture
def paths(tmp_path, monkeypatch):
    return use_config(tmp_path, monkeypatch, searches=SEARCHES, profile=PROFILE)


def stored(paths):
    return yaml.safe_load(paths[0].read_text()), json.loads(paths[1].read_text())


def test_read_settings_shape_and_aliases(paths):
    from hireember import search_config

    assert search_config.read_settings() == {
        "title_include": ["engineer"], "title_exclude": ["sales"], "location_accept": ["Berlin"],
        "location_reject": ["Paris"], "remote": False,
        "personal": {"city": "Berlin", "province_state": "BE", "country": "Germany"}}


def test_missing_files_give_empty_settings(tmp_path, monkeypatch):
    from hireember import search_config

    use_config(tmp_path, monkeypatch)
    s = search_config.read_settings()
    assert s["title_include"] == [] and s["location_reject"] == [] and s["remote"] is False
    assert s["personal"] == {"city": "", "province_state": "", "country": ""}
    assert search_config.load() == {}


def test_save_writes_canonical_keys_and_keeps_others(paths):
    from hireember import search_config

    out = search_config.save_settings({"title_exclude": ["Sales", "Recruiter"], "location_accept": ["Munich"],
                                       "personal": {"country": "France", "city": "Paris",
                                                    "province_state": "IDF"}})
    assert out["title_exclude"] == ["Sales", "Recruiter"] and out["personal"]["country"] == "France"
    cfg, prof = stored(paths)
    assert cfg["title_exclude"] == ["Sales", "Recruiter"] and "exclude_titles" not in cfg
    assert cfg["location"]["accept_patterns"] == ["Munich"] and "location_accept" not in cfg
    assert cfg["location_reject_non_remote"] == ["Paris"] or cfg["location"].get("reject_patterns") == ["Paris"]
    assert cfg["title_include"] == ["engineer"]
    assert cfg["queries"] == SEARCHES["queries"] and cfg["proxy"] == "http://p:1"
    assert cfg["defaults"] == SEARCHES["defaults"]
    assert prof["personal"] == {"city": "Paris", "province_state": "IDF", "country": "France",
                                "full_name": "Jane"}
    assert prof["experience"] == {"target_role": "Engineer"}
    assert "country" not in cfg and "personal" not in cfg


def test_remote_flag_rules(paths):
    from hireember import search_config

    assert search_config.save_settings({"remote": True})["remote"] is True
    cfg, _ = stored(paths)
    assert {"location": "Remote", "remote": True} in cfg["locations"]
    search_config.save_settings({"remote": False})
    cfg, _ = stored(paths)
    assert all(not e.get("remote") for e in cfg["locations"])
    assert search_config.read_settings()["remote"] is False


def test_saved_value_used_on_next_call_without_restart(paths):
    from hireember import search_config
    from hireember.location import location_skip_reason
    from hireember.titles import title_filter

    profile = json.loads(paths[1].read_text())
    assert location_skip_reason("Paris, France", profile) is not None
    assert title_filter("Recruiter", *search_config.title_lists(search_config.load())) is not None  # not in include
    search_config.save_settings({"title_include": ["recruiter"], "title_exclude": [],
                                 "location_accept": ["Paris"], "location_reject": []})
    cfg = search_config.load()
    assert title_filter("Recruiter", *search_config.title_lists(cfg)) is None
    assert location_skip_reason("Paris, France", json.loads(paths[1].read_text())) is None


def test_profile_country_change_seen_by_location(paths):
    from hireember import config, search_config
    from hireember.location import location_skip_reason

    search_config.save_settings({"location_accept": [], "location_reject": []})
    assert location_skip_reason("Toronto, Canada", config.load_profile()) is not None
    search_config.save_settings({"personal": {"city": "", "province_state": "", "country": "Canada"}})
    assert location_skip_reason("Toronto, Canada", config.load_profile()) is None


@pytest.mark.parametrize("payload, field, message", [
    ({"title_include": [5]}, "title_include", "Enter text."),
    ({"title_include": ["a", "  "]}, "title_include", "Enter a keyword."),
    ({"title_exclude": ["Sales", "sales "]}, "title_exclude", "'sales' is already in the list."),
    ({"title_exclude": ["x" * 81]}, "title_exclude", "Keep entries under 80 characters."),
    ({"location_accept": "Berlin"}, "location_accept", "Enter a list of keywords."),
    ({"remote": "yes"}, "remote", "remote must be true or false."),
    ({"personal": {"city": 4, "province_state": "", "country": ""}}, "personal.city", "Enter text."),
])
def test_validation_rejects_and_writes_nothing(paths, payload, field, message):
    from hireember import search_config

    before = (paths[0].read_bytes(), paths[1].read_bytes())
    with pytest.raises(search_config.SettingsError) as exc:
        search_config.save_settings(payload)
    assert str(exc.value) == message and exc.value.field == field
    assert (paths[0].read_bytes(), paths[1].read_bytes()) == before


def test_second_replace_failure_restores_first_file(paths, monkeypatch):
    import os

    from hireember import search_config

    before = (paths[0].read_bytes(), paths[1].read_bytes())
    real = os.replace
    calls = []

    def flaky(src, dst, *a, **k):
        calls.append(str(dst))
        if str(dst).endswith("profile.json"):
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", flaky)
    with pytest.raises(OSError):
        search_config.save_settings({"title_include": ["new"], "personal": {
            "city": "X", "province_state": "", "country": ""}})
    monkeypatch.setattr(os, "replace", real)
    assert (paths[0].read_bytes(), paths[1].read_bytes()) == before


def test_malformed_files_raise_unreadable(tmp_path, monkeypatch):
    from hireember import search_config

    use_config(tmp_path, monkeypatch, raw_searches="a: [unclosed\n", profile=PROFILE)
    with pytest.raises(search_config.UnreadableConfigError) as exc:
        search_config.read_settings()
    assert str(exc.value).startswith("Could not read searches.yaml: ")
    before = (tmp_path / "searches.yaml").read_bytes()
    with pytest.raises(search_config.UnreadableConfigError):
        search_config.save_settings({"title_include": ["x"]})
    assert (tmp_path / "searches.yaml").read_bytes() == before
    assert search_config.load() == {}


def test_known_keys_and_title_lists():
    from hireember import search_config

    assert {"queries", "title_include", "title_exclude", "exclude_titles", "location_accept",
            "location_reject_non_remote", "workday_location_filter"} <= search_config.KNOWN_KEYS
    assert search_config.title_lists({"title_include": ["a", 3], "exclude_titles": ["b"]}) == (["a"], ["b"])
    assert search_config.title_lists({"title_exclude": ["c"], "exclude_titles": ["b"]}) == ([], ["c"])


# -- HTTP --------------------------------------------------------------------

@pytest.fixture
def api(paths, isolated_db):
    from hireember.database import close_connection, init_db

    init_db(isolated_db)
    server, thread = start_server(isolated_db)
    yield Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


def test_api_get_put(api, paths):
    status, body = api.get("/api/profile")
    assert status == 200 and body["title_exclude"] == ["sales"] and body["personal"]["country"] == "Germany"
    status, body = api.json("PUT", "/api/profile", {"title_exclude": ["sales", "recruiter"]})
    assert status == 200 and body["title_exclude"] == ["sales", "recruiter"]
    cfg, _ = stored(paths)
    assert cfg["title_exclude"] == ["sales", "recruiter"] and "exclude_titles" not in cfg


def test_api_bad_request_and_unreadable(api, paths):
    before = paths[0].read_bytes()
    status, body = api.json("PUT", "/api/profile", {"title_include": ["a", "A"]})
    assert status == 400 and body == {"error": "'A' is already in the list.", "code": "bad_request",
                                      "field": "title_include"}
    assert paths[0].read_bytes() == before
    paths[0].write_text("a: [unclosed\n")
    status, body = api.get("/api/profile")
    assert status == 422 and body["code"] == "unreadable"
    assert body["error"].startswith("Could not read searches.yaml: ")
    assert api.json("PUT", "/api/profile", {"title_include": ["x"]})[0] == 422


def test_api_save_failure_is_500_and_files_unchanged(api, paths, monkeypatch):
    import os

    before = (paths[0].read_bytes(), paths[1].read_bytes())
    real = os.replace

    def broken(src, dst, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken)
    status, body = api.json("PUT", "/api/profile", {"title_include": ["new"]})
    monkeypatch.setattr(os, "replace", real)
    assert status == 500 and body["code"] == "save_failed"
    assert body["error"].startswith("Could not save: ") and body["error"].endswith("Nothing was changed.")
    assert (paths[0].read_bytes(), paths[1].read_bytes()) == before
