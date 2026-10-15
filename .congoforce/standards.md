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
- CLI help text lives in `typer.Typer(help=...)` in `cli.py`, which overrides the callback docstring. Change both when rewording the CLI.

## Docs agents should read

- `README.md`
- `CONTRIBUTING.md`

## Gotchas

- The repo has two remotes: `origin` = reetesh11/HireEmber, `upstream` = Pickle-Pixel/ApplyPilot. `gh` must default to reetesh11/HireEmber (`gh repo set-default reetesh11/HireEmber`). Never open PRs or push to upstream.
- The freeze commit may leave the test author's edits to files that were already tracked (for example the shared conftest) uncommitted. The implementer commits them byte for byte in its first task commit and never edits them.
- The CongoForce hook blocks any Bash command whose text contains a frozen test path, even in a summary or answer. Read frozen files with the Read tool and refer to them by description in command text.
- The package is `hireember` (`src/hireember`). Its data folder comes from `HIREEMBER_DIR`, defaulting to `~/.hireember` with a read-only `~/.applypilot` fallback. Tests isolate through `HIREEMBER_DIR` and never touch the real home folders.

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
