"""AC-2: CI runs lint and tests on push and pull requests."""

from pathlib import Path

import yaml

CI_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(CI_PATH.read_text(encoding="utf-8"))


def _triggers(wf: dict):
    # PyYAML (YAML 1.1) parses the bare key `on` as boolean True.
    on = wf.get("on", wf.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    return set((on or {}).keys())


def _steps(wf: dict) -> list[tuple[dict, dict]]:
    out = []
    for job in (wf.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            out.append((job, step))
    return out


def test_ci_triggers_on_push_and_pull_request():
    triggers = _triggers(_workflow())
    assert "push" in triggers
    assert "pull_request" in triggers


def test_ci_lint_step_runs_ruff_on_whole_repo():
    runs = [str(step.get("run", "")) for _, step in _steps(_workflow())]
    lint_lines = [line.strip() for run in runs for line in run.splitlines() if "ruff check" in line]
    assert lint_lines, "no step runs `ruff check`"
    assert any(line.endswith("ruff check .") for line in lint_lines), lint_lines
    assert not any("ruff check src" in line for line in lint_lines), lint_lines


def test_ci_test_step_runs_pytest_on_tests_with_src_on_pythonpath():
    wf = _workflow()
    found = False
    for job, step in _steps(wf):
        run = str(step.get("run", ""))
        if "pytest" in run and "tests/" in run:
            env = {}
            env.update(wf.get("env") or {})
            env.update(job.get("env") or {})
            env.update(step.get("env") or {})
            inline = "PYTHONPATH=src" in run
            if inline or "src" in str(env.get("PYTHONPATH", "")).split(":"):
                found = True
    assert found, "no step runs pytest on tests/ with PYTHONPATH=src"
