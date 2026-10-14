"""AC-1: the pytest harness is isolated and dev extras carry pytest and ruff."""

import os
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_conftest_isolates_app_dir_from_home():
    from applypilot import config

    assert (REPO_ROOT / "tests" / "conftest.py").is_file()
    app_dir = Path(os.environ["APPLYPILOT_DIR"]).resolve()
    assert app_dir != (Path.home() / ".applypilot").resolve()
    assert Path(config.APP_DIR).resolve() == app_dir
    assert Path(config.DB_PATH).resolve().parent == app_dir
    assert "CHROME_PATH" not in os.environ


def test_dev_extras_include_pytest_and_ruff():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = data["project"]["optional-dependencies"]["dev"]
    names = {d.split(">")[0].split("=")[0].split("<")[0].split("[")[0].strip().lower() for d in dev}
    assert "pytest" in names
    assert "ruff" in names
