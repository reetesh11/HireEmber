"""Rename AC-6: HIREEMBER_DIR sets the data folder, with no move notice."""

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


def test_hireember_dir_env_sets_app_dir_without_notice(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom"

    proc = _probe(home, tmp_path, hireember_dir=str(custom))
    got = _result(proc)

    assert Path(got["app_dir"]).resolve() == custom.resolve()
    assert got["legacy"] is False
    assert Path(got["db_path"]) == Path(got["app_dir"]) / "hireember.db"
    assert "~/.applypilot" not in proc.stderr + proc.stdout
    assert not custom.exists(), "importing hireember.config must not create the data folder"
    assert list(home.iterdir()) == []


def test_resolve_app_dir_prefers_env_even_with_legacy_folders(tmp_path):
    from hireember.config import APP_DIR_ENV, resolve_app_dir

    assert APP_DIR_ENV == "HIREEMBER_DIR"
    (tmp_path / ".applypilot").mkdir()
    (tmp_path / ".hireember").mkdir()
    custom = tmp_path / "custom"

    assert resolve_app_dir(environ={"HIREEMBER_DIR": str(custom)}, home=tmp_path) == (custom, False)
    assert not custom.exists()
