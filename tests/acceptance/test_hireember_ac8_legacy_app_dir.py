"""Rename AC-8: an existing ~/.applypilot folder is used in place, with a one-line move notice."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = (
    "import json\n"
    "import hireember.config as c\n"
    "print(json.dumps({'app_dir': str(c.APP_DIR), 'legacy': c.USING_LEGACY_APP_DIR, 'db_path': str(c.DB_PATH)}))\n"
)


def _probe(home: Path, cwd: Path, hireember_dir: str | None = None, extra_env: dict | None = None,
           script: str = PROBE) -> subprocess.CompletedProcess:
    """Import hireember.config in a fresh interpreter with HOME=home; return the finished process."""
    env = dict(os.environ)
    env.pop("HIREEMBER_DIR", None)
    env.pop("APPLYPILOT_DIR", None)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    if hireember_dir is not None:
        env["HIREEMBER_DIR"] = hireember_dir
    env.update(extra_env or {})
    proc = subprocess.run([sys.executable, "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc


def _result(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stdout.strip().splitlines()[0])


NOTICE = (
    "HireEmber: using legacy data folder ~/.applypilot. To move it, run: "
    "mv ~/.applypilot ~/.hireember && mv ~/.hireember/applypilot.db ~/.hireember/hireember.db"
)
PROFILE = {"personal": {"full_name": "Ada Lovelace"}, "work_authorization": {"legally_authorized": True}}


def _snapshot(folder: Path) -> dict:
    return {str(p.relative_to(folder)): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def _legacy_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".applypilot").mkdir(parents=True)
    (home / ".applypilot" / "profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    return home


def test_legacy_folder_is_used_and_profile_loads(tmp_path):
    home = _legacy_home(tmp_path)
    before = _snapshot(home / ".applypilot")
    script = PROBE + "print(json.dumps(c.load_profile()))\n"

    proc = _probe(home, tmp_path, script=script)
    out = proc.stdout.strip().splitlines()
    got = json.loads(out[0])

    assert Path(got["app_dir"]).resolve() == (home / ".applypilot").resolve()
    assert got["legacy"] is True
    assert Path(got["db_path"]) == Path(got["app_dir"]) / "applypilot.db"
    assert json.loads(out[1]) == PROFILE
    assert (home / ".applypilot").is_dir()
    assert _snapshot(home / ".applypilot") == before
    assert not (home / ".hireember").exists()
    assert sorted(p.name for p in home.iterdir()) == [".applypilot"]


def test_exactly_one_notice_line_on_stderr_only(tmp_path):
    home = _legacy_home(tmp_path)
    script = (
        PROBE
        + "import importlib\n"
        + "importlib.import_module('hireember.config')\n"
        + "import hireember.database\n"
        + "import hireember.cli\n"
    )

    proc = _probe(home, tmp_path, script=script)

    notice_lines = [line for line in proc.stderr.splitlines() if "~/.applypilot" in line]
    assert notice_lines == [NOTICE], proc.stderr
    assert "~/.hireember" in notice_lines[0]
    assert "~/.applypilot" not in proc.stdout
    assert not (home / ".hireember").exists()


def test_notice_constant_and_resolver(tmp_path):
    from hireember.config import LEGACY_DIR_NOTICE, resolve_app_dir

    assert LEGACY_DIR_NOTICE == NOTICE
    assert "\n" not in LEGACY_DIR_NOTICE

    (tmp_path / ".applypilot").mkdir()
    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".applypilot", True)
    assert resolve_app_dir(environ={"APPLYPILOT_DIR": str(tmp_path / "x")}, home=tmp_path) == (
        tmp_path / ".applypilot",
        True,
    )
    assert not (tmp_path / ".hireember").exists()
