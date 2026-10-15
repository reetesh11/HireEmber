---
class: task
size: medium
title: Rename the project from applypilot to HireEmber
---
# Requirements — Rename the project from applypilot to HireEmber

## Problem
The fork's chosen name is HireEmber (PyPI and CLI name `hireember`), as decided in Q9 of the requirements document. The code still ships as `applypilot`: package `src/applypilot`, console script, `pyproject.toml` metadata, the `~/.applypilot` data folder, the `APPLYPILOT_DIR` variable, and user-facing text. Existing users must keep their data, and the upstream ApplyPilot credit must stay. This is a mechanical rename across about 21 source files plus tests and docs. It involves no product redesign.

## Requirements
- R1. The package shall live at `src/hireember` and be imported as `hireember`. No module under `src` or `tests` shall import `applypilot`.
- R2. When the user runs `hireember <subcommand>` or `python -m hireember <subcommand>`, the system shall behave as `applypilot <subcommand>` did. The subcommands are `init`, `run`, `apply`, `status`, `dashboard`, `doctor`, plus `--version`.
- R3. `pyproject.toml` shall name the project `hireember`, declare the script `hireember = "hireember.cli:app"`, and point the wheel `packages` and `artifacts` at `src/hireember`.
- R4. While `HIREEMBER_DIR` is set, the system shall use that folder as the data folder (`APP_DIR`).
- R5. While `HIREEMBER_DIR` is unset, the system shall use `~/.hireember` as the data folder.
- R6. If `HIREEMBER_DIR` is unset, `~/.hireember` does not exist and `~/.applypilot` does exist, then the system shall use `~/.applypilot` and print a one-line notice that tells the user how to move it to `~/.hireember`. The system shall not move, copy or delete any folder.
- R7. User-facing text (CLI help, `--version` output, error and doctor messages, wizard prompts and generated file headers, dashboard titles, `.env.example`, `searches.example.yaml`, README and CONTRIBUTING command examples) shall say HireEmber or `hireember` and `~/.hireember` in place of ApplyPilot, `applypilot` and `~/.applypilot`.
- R8. The README, LICENSE and source headers shall keep the ApplyPilot copyright and attribution, the AGPL-3.0 licence, the fork notice, and the disclaimer about unrelated "ApplyPilot" products.

## Acceptance criteria
- AC-1: `PYTHONPATH=src .venv/bin/python -m pytest` and `.venv/bin/ruff check .` both exit 0.
- AC-2: `src/hireember/` exists and `src/applypilot/` does not. `import hireember; hireember.__version__` returns a non-empty string.
- AC-3: `grep -rnE "import applypilot|from applypilot" src tests` returns no matches.
- AC-4: `python -m hireember --help`, run through Typer's `CliRunner` on `hireember.cli.app`, exits 0 and lists exactly `init`, `run`, `apply`, `status`, `dashboard`, `doctor`. `--version` prints `hireember 0.3.0`.
- AC-5: `pyproject.toml` has `name = "hireember"`, `[project.scripts]` `hireember = "hireember.cli:app"` (and no `applypilot` script), `packages = ["src/hireember"]` and `artifacts = ["src/hireember/config/*.yaml"]`.
- AC-6: With `HIREEMBER_DIR=<tmp>/custom` set, the resolved `APP_DIR` is `<tmp>/custom` and no move notice is printed.
- AC-7: With `HIREEMBER_DIR` unset, HOME set to an empty temp folder and `~/.hireember` missing, the resolved `APP_DIR` is `<home>/.hireember` and no notice is printed.
- AC-8: With `HIREEMBER_DIR` unset, HOME set to a temp folder that holds only `.applypilot/profile.json`, the resolved `APP_DIR` is `<home>/.applypilot`. `load_profile()` reads that file. Exactly one notice line is emitted, and it mentions both `~/.applypilot` and `~/.hireember`. After the run `<home>/.applypilot` still exists unchanged and `<home>/.hireember` was not created.
- AC-9: With HOME holding both `.hireember` and `.applypilot`, the resolved `APP_DIR` is `<home>/.hireember` and no notice is printed.
- AC-10: `grep -rn "applypilot init\|applypilot run\|applypilot apply\|applypilot doctor\|~/.applypilot" src README.md CONTRIBUTING.md .env.example` finds no matches outside the legacy-fallback code and its notice text.
- AC-11: README.md uses `hireember` in its install and command examples (`pip install hireember`, `hireember init`, …). It still contains the fork notice crediting ApplyPilot by Pickle-Pixel with a link to `https://github.com/Pickle-Pixel/ApplyPilot`, the AGPL-3.0 statement and the "not affiliated with applypilot.app" disclaimer. LICENSE is unchanged.

## Out of scope
- Renaming the git repo folder or the GitHub repository.
- Publishing to PyPI.
- Changing the CongoForce task name or the source requirements document title.
- Automatically migrating or moving user data folders.
- Changing `[project.urls]` or `authors`, which still point at upstream ApplyPilot.
- Rewriting upstream marketing copy in the README beyond the title, commands and paths (for example the "ApplyPilot vs The Alternatives" table).

## Assumptions
- The version stays `0.3.0`.
- The SQLite file name `applypilot.db` stays the same, so a legacy folder's database still loads. New installs in `~/.hireember` also use `applypilot.db` (see open questions).
- The `APPLYPILOT_DIR` variable is no longer read. Only `HIREEMBER_DIR` is honoured (see open questions).
- The move notice goes to stderr through the existing console or logging, once per process.
- `tests/conftest.py` imports `applypilot` and sets `APPLYPILOT_DIR`. Freezing it for this task would make the rename impossible, so it must be updated to `hireember` and `HIREEMBER_DIR` in the test-writing stage, before Gate 2. The same goes for the existing unit and acceptance tests that import `applypilot`.
- Docstrings and comments that name ApplyPilot as the product are rebranded. Comments that credit upstream are kept.

## Open questions
- Should the database file be renamed to `hireember.db` for new installs? If so, should the legacy `~/.applypilot` folder keep using `applypilot.db`? (Default assumed: keep `applypilot.db` everywhere.)
- Should `APPLYPILOT_DIR` still be honoured as a fallback when `HIREEMBER_DIR` is unset, for users who scripted it? (Default assumed: no.)
