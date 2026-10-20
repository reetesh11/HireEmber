"""AC-10, AC-11 (docs side): jobspy is a plain dependency and the --no-deps hints are gone."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pyproject_lists_python_jobspy_as_plain_dependency():
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    match = [d for d in deps if d.replace(" ", "").lower().startswith("python-jobspy")]
    assert len(match) == 1, deps
    assert ";" not in match[0] and "[" not in match[0]
    for extra, items in data["project"].get("optional-dependencies", {}).items():
        assert not any("jobspy" in i.lower() for i in items), extra


def test_lock_file_includes_python_jobspy_and_curl_cffi():
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "python-jobspy"' in lock
    assert 'name = "curl-cffi"' in lock


def test_readme_has_no_no_deps_instructions():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "--no-deps" not in readme
    assert "tls-client" not in readme
    assert "pip install hireember" in readme


def test_doctor_source_has_no_stale_hint():
    text = (REPO_ROOT / "src" / "hireember" / "doctor.py").read_text(encoding="utf-8")
    assert "--no-deps" not in text
