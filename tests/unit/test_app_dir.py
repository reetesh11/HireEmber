"""Unit tests for hireember.config.resolve_app_dir and the legacy notice."""

import os
import subprocess
import sys
from pathlib import Path

from hireember.config import LEGACY_DIR_NOTICE, resolve_app_dir

SRC_DIR = Path(__file__).resolve().parents[2] / "src"


def _listing(path: Path) -> list[str]:
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


def test_env_var_wins_over_existing_folders(tmp_path):
    (tmp_path / ".hireember").mkdir()
    (tmp_path / ".applypilot").mkdir()
    custom = tmp_path / "custom"
    assert resolve_app_dir(environ={"HIREEMBER_DIR": str(custom)}, home=tmp_path) == (custom, False)


def test_env_var_expands_user(tmp_path):
    app_dir, legacy = resolve_app_dir(environ={"HIREEMBER_DIR": "~/data"}, home=tmp_path)
    assert app_dir == Path("~/data").expanduser()
    assert legacy is False


def test_empty_and_whitespace_env_values_are_unset(tmp_path):
    for value in ("", "   "):
        assert resolve_app_dir(environ={"HIREEMBER_DIR": value}, home=tmp_path) == (tmp_path / ".hireember", False)


def test_default_with_empty_home(tmp_path):
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)


def test_legacy_only(tmp_path):
    (tmp_path / ".applypilot").mkdir()
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".applypilot", True)


def test_both_folders_prefer_hireember(tmp_path):
    (tmp_path / ".hireember").mkdir()
    (tmp_path / ".applypilot").mkdir()
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)


def test_legacy_file_is_not_a_legacy_folder(tmp_path):
    (tmp_path / ".applypilot").write_text("not a dir", encoding="utf-8")
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)


def test_old_env_var_is_ignored(tmp_path):
    environ = {"APPLYPILOT_DIR": str(tmp_path / "old")}
    assert resolve_app_dir(environ=environ, home=tmp_path) == (tmp_path / ".hireember", False)


def test_resolver_creates_nothing(tmp_path):
    (tmp_path / ".applypilot").mkdir()
    before = _listing(tmp_path)
    resolve_app_dir(environ={}, home=tmp_path)
    resolve_app_dir(environ={"HIREEMBER_DIR": str(tmp_path / "custom")}, home=tmp_path)
    assert _listing(tmp_path) == before


def test_notice_is_one_line_with_both_paths():
    assert "\n" not in LEGACY_DIR_NOTICE
    assert "~/.applypilot" in LEGACY_DIR_NOTICE
    assert "~/.hireember" in LEGACY_DIR_NOTICE


def test_import_in_legacy_home_prints_one_notice(tmp_path):
    (tmp_path / ".applypilot").mkdir()
    env = dict(os.environ)
    env.pop("HIREEMBER_DIR", None)
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = str(SRC_DIR)
    code = "import hireember.config as c; import hireember.config; print(c.DB_PATH.name)"
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "applypilot.db"
    assert proc.stderr.splitlines() == [LEGACY_DIR_NOTICE]
    assert not (tmp_path / ".hireember").exists()
