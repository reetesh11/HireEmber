"""Rename AC-9: when both ~/.hireember and ~/.applypilot exist, ~/.hireember wins silently."""

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


def test_both_folders_use_hireember_without_notice(tmp_path):
    home = tmp_path / "home"
    (home / ".hireember").mkdir(parents=True)
    (home / ".applypilot").mkdir()
    (home / ".applypilot" / "profile.json").write_text("{}", encoding="utf-8")

    proc = _probe(home, tmp_path)
    got = _result(proc)

    assert Path(got["app_dir"]).resolve() == (home / ".hireember").resolve()
    assert got["legacy"] is False
    assert Path(got["db_path"]) == Path(got["app_dir"]) / "hireember.db"
    assert "~/.applypilot" not in proc.stderr + proc.stdout
    assert (home / ".applypilot" / "profile.json").read_text(encoding="utf-8") == "{}"


def test_resolve_app_dir_prefers_existing_hireember(tmp_path):
    from hireember.config import resolve_app_dir

    (tmp_path / ".hireember").mkdir()
    (tmp_path / ".applypilot").mkdir()

    assert resolve_app_dir(environ={}, home=tmp_path) == (tmp_path / ".hireember", False)
