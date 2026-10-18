import pytest

import hireember.config as config
from hireember.apply import chrome
from hireember.apply.chrome import DefaultProfileError, assert_dedicated_profile, check_worker_profiles


def test_default_profile_and_neighbours_refused():
    default = config.get_chrome_user_data()
    for path in (default, default / "Default", default.parent):
        with pytest.raises(DefaultProfileError):
            assert_dedicated_profile(path)


def test_dedicated_profile_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROME_WORKER_DIR", tmp_path / "cw")
    check_worker_profiles(2)
    assert_dedicated_profile(tmp_path / "cw" / "worker-1")


def test_new_profile_is_empty_and_never_copied_from_real_chrome(tmp_path, monkeypatch):
    real = tmp_path / "real"
    (real / "Default").mkdir(parents=True)
    (real / "Default" / "Cookies").write_text("secret")
    monkeypatch.setattr(config, "get_chrome_user_data", lambda: real)
    monkeypatch.setattr(config, "CHROME_WORKER_DIR", tmp_path / "cw")
    profile = chrome.setup_worker_profile(0)
    assert profile.exists() and list(profile.iterdir()) == []


def test_new_profile_clones_another_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROME_WORKER_DIR", tmp_path / "cw")
    (tmp_path / "cw" / "worker-0" / "Default").mkdir(parents=True)
    (tmp_path / "cw" / "worker-0" / "Default" / "Cookies").write_text("c")
    profile = chrome.setup_worker_profile(1)
    assert (profile / "Default" / "Cookies").read_text() == "c"


def test_launch_chrome_asserts_before_starting(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHROME_WORKER_DIR", config.get_chrome_user_data().parent)
    monkeypatch.setattr(chrome.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("Chrome must not start"))
    with pytest.raises(DefaultProfileError):
        chrome.launch_chrome(0)
