"""Rename AC-5: pyproject.toml names the project, script and wheel contents `hireember`."""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _data() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_project_name_is_hireember():
    assert _data()["project"]["name"] == "hireember"


def test_console_script_is_hireember_only():
    assert _data()["project"]["scripts"] == {"hireember": "hireember.cli:app"}


def test_wheel_packages_and_artifacts_point_at_src_hireember():
    build = _data()["tool"]["hatch"]["build"]
    assert build["targets"]["wheel"]["packages"] == ["src/hireember"]
    assert build["artifacts"] == ["src/hireember/config/*.yaml"]
