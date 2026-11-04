import json

import pytest
import yaml

from hireember import config, search_config


@pytest.fixture
def paths(tmp_path, monkeypatch):
    sp, pp = tmp_path / "searches.yaml", tmp_path / "profile.json"
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", sp)
    monkeypatch.setattr(config, "PROFILE_PATH", pp)
    return sp, pp


def test_save_creates_missing_files_with_only_saved_keys(paths):
    out = search_config.save_settings({"title_include": [" Engineer "], "personal": {"city": "Rome"}})
    assert out["title_include"] == ["Engineer"] and out["personal"]["city"] == "Rome"
    assert yaml.safe_load(paths[0].read_text()) == {"title_include": ["Engineer"]}
    assert json.loads(paths[1].read_text()) == {"personal": {"city": "Rome"}}


def test_unchanged_files_not_rewritten(paths):
    paths[0].write_text("# comment\ntitle_include: [a]\n")
    search_config.save_settings({"title_include": ["a"]})
    assert paths[0].read_text() == "# comment\ntitle_include: [a]\n"
    assert not paths[1].exists()


def test_validation_messages(paths):
    for payload, msg in [({"personal": {"city": "x" * 81}}, "Keep entries under 80 characters."),
                         ({"title_include": ["a", "A "]}, "'A' is already in the list."),
                         ({"personal": "x"}, "Enter text.")]:
        with pytest.raises(search_config.SettingsError) as exc:
            search_config.save_settings(payload)
        assert str(exc.value) == msg
    assert not paths[0].exists()


def test_malformed_profile_refuses_write(paths):
    paths[1].write_text("{bad")
    with pytest.raises(search_config.UnreadableConfigError) as exc:
        search_config.save_settings({"title_include": ["a"]})
    assert str(exc.value).startswith("Could not read profile.json: ")
    assert not paths[0].exists()
