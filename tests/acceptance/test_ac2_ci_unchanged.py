"""AC-2 (unchanged behaviour): the CI matrix and fail-fast semantics stay."""

from pathlib import Path

import yaml

CI_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def test_ci_matrix_covers_python_311_312_313():
    wf = yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))
    versions = set()
    for job in (wf.get("jobs") or {}).values():
        matrix = ((job.get("strategy") or {}).get("matrix") or {})
        versions.update(str(v) for v in matrix.get("python-version", []))
    assert {"3.11", "3.12", "3.13"} <= versions


def test_ci_failures_are_not_masked():
    text = CI_PATH.read_text(encoding="utf-8")
    assert "continue-on-error" not in text
    assert "|| true" not in text
