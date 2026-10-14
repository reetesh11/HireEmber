# Standards — openapply

Every CongoForce agent follows this file. The human owns it: edit anything,
then approve with `congoforce standards approve`. Agents never edit it,
except a bootstrap task, which may fill in the test commands.

## Stack

- Python, pytest, ruff, src layout
- Acceptance tests live in `tests/acceptance/` unless the repo already has a convention.

## Conventions

- Match the style, naming and structure of the surrounding code.
- Reuse existing utilities before adding new ones.
- Keep each commit to one task from tech.md, with the build green after it.
- (add repo-specific rules here: layout, error handling, logging, copy tone)

## Docs agents should read

- `README.md`
- `CONTRIBUTING.md`

## Gotchas

- (none yet; Retro proposes additions after each run)

## Draft notes

- Tests run with PYTHONPATH set so the worktree's own code is imported (PYTHONPATH=src).
- pytest writes JUnit XML with junit_family=xunit1 so each test carries its file path.

## Commands (machine-readable)

Each command runs from the task worktree root under `command_timeout`.
`{junit}` is replaced with the JUnit XML path the helper reads; `{files}`
with the test files to run. Leave a command empty to skip it.

```toml
[preset]
name = "python"

[commands]
install = "uv venv --allow-existing --python 3.11 .venv && uv pip install --python .venv/bin/python -e '.[dev]'"
lint = ".venv/bin/ruff check ."
typecheck = ""
build = ""
test = "PYTHONPATH=src .venv/bin/python -m pytest -q -o junit_family=xunit1 --continue-on-collection-errors --junitxml={junit}"
test_files = "PYTHONPATH=src .venv/bin/python -m pytest -q -o junit_family=xunit1 --continue-on-collection-errors --junitxml={junit} {files}"
e2e = ""

[paths]
package_dir = "."

[freeze]
# Frozen at Gate 2 with the acceptance tests: test config the implementer must not touch.
globs = ["**/conftest.py", "pytest.ini", "tox.ini", "setup.cfg"]
keys = []
```
