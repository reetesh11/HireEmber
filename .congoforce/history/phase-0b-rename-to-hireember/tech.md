# Tech spec — Rename the project from applypilot to HireEmber

## Approach
This is a mechanical rename plus two small behaviour changes, done in place
with no new modules. (1) `git mv src/applypilot src/hireember`, then rewrite
every `applypilot` import to `hireember` and update `pyproject.toml`. (2) Data
folder resolution in `src/hireember/config.py` changes from the one-liner
`APP_DIR = Path(os.environ.get("APPLYPILOT_DIR", ...))` to a small pure function,
`resolve_app_dir()`, that applies the order `HIREEMBER_DIR`, then `~/.hireember`,
then `~/.applypilot` (only when `~/.hireember` is missing), then `~/.hireember`.
The function returns whether the legacy folder was picked. The module-level
constants (`APP_DIR`, `DB_PATH`, `PROFILE_PATH`, …) stay module globals that
are computed once at import, so the many `from hireember.config import X` call
sites keep working. The one-line legacy notice is written to stderr when
`hireember.config` is first imported, which makes it once per process. The DB
file is `hireember.db`, except in the legacy folder, where it stays
`applypilot.db` (gate-1 answer 1). `APPLYPILOT_DIR` is no longer read (gate-1
answer 2). (3) User-facing strings in `cli.py`, `doctor.py`, `wizard/init.py`,
`view.py`, `pipeline.py`, `apply/dashboard.py`, `discovery/jobspy.py`,
`config.py` and the shipped YAML headers switch to HireEmber/`hireember`.
Upstream attribution stays. (4) The gate-1 scope addition: `doctor.check_sources`
follows the existing `doctor.py` pattern ("each check returns a `Check`, never
raises"). It catches YAML parse errors and non-mapping top levels in
`searches.yaml`, `employers.yaml` and `sites.yaml`, and returns a MISSING check
instead of crashing. Conventions followed: `src/applypilot/doctor.py` (a `Check`
dataclass per check, `config.X` read at call time so tests can monkeypatch),
`src/applypilot/config.py` (module-level path constants, `log = logging.getLogger(__name__)`),
and `tests/unit/test_doctor.py` and `tests/acceptance/test_ac6_doctor.py` for
test style.

## Interface contract

### Package and entry points
- Package directory `src/hireember/`. `src/applypilot/` does not exist.
- `import hireember` gives `hireember.__version__ == "0.3.0"` (a non-empty `str`).
- `hireember.cli.app` is a `typer.Typer`, named `"hireember"`.
  - `CliRunner().invoke(app, ["--help"])` exits 0. Its command list is exactly
    `init`, `run`, `apply`, `status`, `dashboard`, `doctor`.
  - `CliRunner().invoke(app, ["--version"])` (also `-V`) exits 0. Its output,
    stripped, is `hireember 0.3.0`.
  - The help text says `HireEmber`. Neither the help nor the `--version` output contains `applypilot` or `ApplyPilot`.
- `python -m hireember <args>` (module `hireember/__main__.py`) runs the same `app`.
- Console script `hireember` (after `pip install -e .`).
- `pyproject.toml`:
  - `[project] name = "hireember"` and `version = "0.3.0"`.
  - `[project.scripts]` holds exactly `hireember = "hireember.cli:app"` (no `applypilot` key).
  - `[tool.hatch.build.targets.wheel] packages = ["src/hireember"]`.
  - `[tool.hatch.build] artifacts = ["src/hireember/config/*.yaml"]`.
  - `[project.urls]` and `authors` are unchanged (upstream).

### Data folder (`hireember.config`)
- `hireember.config.APP_DIR_ENV == "HIREEMBER_DIR"`.
- `hireember.config.resolve_app_dir(environ: Mapping[str, str] | None = None, home: Path | None = None) -> tuple[Path, bool]`
  is pure. It creates nothing, moves nothing and prints nothing. `environ`
  defaults to `os.environ` and `home` defaults to `Path.home()`. It returns
  `(app_dir, is_legacy)`:
  1. `environ["HIREEMBER_DIR"]` is set and non-empty: returns `(Path(value).expanduser(), False)`. This holds even when legacy folders exist.
  2. Otherwise, `home/".hireember"` exists: returns `(home/".hireember", False)`.
  3. Otherwise, `home/".applypilot"` is a directory: returns `(home/".applypilot", True)`.
  4. Otherwise: returns `(home/".hireember", False)`.
  
  `APPLYPILOT_DIR` is ignored in every case.
- Module constants are computed once at import from `resolve_app_dir()`:
  - `APP_DIR: Path`.
  - `USING_LEGACY_APP_DIR: bool`.
  - `DB_PATH = APP_DIR / "hireember.db"`, or `APP_DIR / "applypilot.db"` when `USING_LEGACY_APP_DIR`.
  - `PROFILE_PATH = APP_DIR / "profile.json"`.
  - `RESUME_PATH`, `RESUME_PDF_PATH`, `SEARCH_CONFIG_PATH`, `ENV_PATH`, `TAILORED_DIR`, `COVER_LETTER_DIR`, `LOG_DIR`, `CHROME_WORKER_DIR`, `APPLY_WORKER_DIR`: same names and relative layout as before.
  - `CONFIG_DIR`: the package `config/` folder.
- `hireember.config.LEGACY_DIR_NOTICE: str` is a single line (no `\n`) that
  contains both `~/.applypilot` and `~/.hireember`. Exact text:
  `HireEmber: using legacy data folder ~/.applypilot. To move it, run: mv ~/.applypilot ~/.hireember && mv ~/.hireember/applypilot.db ~/.hireember/hireember.db`
- Notice emission: when `hireember.config` is first imported and
  `USING_LEGACY_APP_DIR` is true, `LEGACY_DIR_NOTICE + "\n"` is written to
  **stderr**. This happens exactly once per process, and nothing goes to stdout.
  In every other case nothing is printed. Importing never creates, moves, copies
  or deletes a folder.
- `hireember.config.load_profile() -> dict` reads `PROFILE_PATH`. If the file is
  missing it raises `FileNotFoundError`, and the message contains `hireember init`.
- Testing note: on macOS and Linux, `Path.home()` honours `HOME`. Because
  `APP_DIR` is fixed at import, end-to-end checks of AC-6 to AC-9 should run a
  subprocess, for example
  `[sys.executable, "-c", "import hireember.config as c; print(c.APP_DIR); print(c.USING_LEGACY_APP_DIR)"]`
  with `env` = a copy of `os.environ`, `HOME=<tmp home>`, `PYTHONPATH=<repo>/src`,
  and `HIREEMBER_DIR` removed or set as the case needs. Then assert on stdout and
  stderr (the notice line appears on stderr only in the legacy case). For AC-8,
  append `print(c.load_profile())` and compare it with the JSON written to
  `<home>/.applypilot/profile.json`. Do not use `importlib.reload` in-process:
  reloading breaks class identity such as `LinkedInBlockedError` for later tests.
  You can also unit-test `resolve_app_dir(environ={...}, home=tmp_path)` in-process.

### Test harness (frozen file the test-author must update)
- `tests/conftest.py` must set `os.environ["HIREEMBER_DIR"]` to a fresh temp dir
  (in place of `APPLYPILOT_DIR`), keep removing `CHROME_PATH`, and import
  `hireember.config` and `hireember.database` in `isolated_db`. The fixtures
  `fixture_form_server` and `isolated_db` keep their names and behaviour.
- The existing tests under `tests/unit/` and `tests/acceptance/` change from
  `applypilot` to `hireember` imports, logger names (`"hireember.config"`),
  paths (`src/hireember/config/searches.example.yaml`) and text (`"HireEmber Doctor"`).

### User-facing text
- `hireember doctor` (via `CliRunner` on `hireember.cli.app`) prints the header
  `HireEmber Doctor`. The MISSING notes for profile, resume, searches and
  database say `hireember init` (the database note says
  `run 'hireember init' or 'hireember run'`).
- `hireember status` prints the header `HireEmber Pipeline Status`.
- `hireember.view` dashboard HTML: `<title>HireEmber Dashboard</title>` and `<h1>HireEmber Dashboard</h1>`.
- `src/hireember/config/searches.example.yaml`, `employers.yaml` and `sites.yaml`
  have header comments that say HireEmber, `~/.hireember/searches.yaml` and `hireember init`.
- `.env.example`: line 1 is `# HireEmber Environment Configuration` and line 2 is
  `# Copy to ~/.hireember/.env and fill in your values.`
- Running
  `grep -rn "applypilot init\|applypilot run\|applypilot apply\|applypilot doctor\|~/.applypilot" src README.md CONTRIBUTING.md .env.example`
  matches only in `src/hireember/config.py`, on the lines that define the legacy
  fallback and `LEGACY_DIR_NOTICE`.
- `README.md`:
  - The install and command examples use `pip install hireember`,
    `hireember init`, `hireember doctor`, `hireember run`, `hireember apply`,
    `hireember status` and `hireember dashboard`.
  - The top title is `# HireEmber`.
  - The `## Fork notice` section keeps its text: fork of
    `[ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot)` by
    `[Pickle-Pixel](https://github.com/Pickle-Pixel)`, plus AGPL-3.0.
  - The line-3 disclaimer containing `not affiliated` and `applypilot.app` is kept verbatim.
  - The `## License` heading and `GNU Affero General Public License v3.0` are kept.
- `LICENSE` is byte-for-byte unchanged.

### Doctor with malformed YAML (gate-1 scope addition)
- `hireember.doctor.check_sources(search_cfg: dict | None = None) -> Check` never raises on bad config.
- Sources it reads, all at call time, so `monkeypatch.setattr(hireember.config, ...)` works:
  - search config, only when `search_cfg is None`: `hireember.config.SEARCH_CONFIG_PATH` if it exists, else `hireember.config.CONFIG_DIR / "searches.example.yaml"`.
  - employers: `hireember.config.CONFIG_DIR / "employers.yaml"`, using its `employers` key.
  - career sites: `hireember.config.CONFIG_DIR / "sites.yaml"`, using its `sites` key.
  
  A missing file counts as empty, as today.
- If any of those files fails to parse (`yaml.YAMLError`), cannot be read
  (`OSError`), or has a non-null top level that is not a mapping (for example a
  list or a scalar), the function returns
  `Check("Job sources", "MISSING", note)`. In `note`, the file name comes first
  (`searches.yaml`, `searches.example.yaml`, `employers.yaml` or `sites.yaml`),
  followed by `: ` and the error. For a non-mapping top level, the error text
  contains `mapping`. A passed-in `search_cfg` that is not a `dict` is reported
  the same way, labelled `searches.yaml`.
- An empty file (top level `None`) counts as `{}`.
- Valid configs behave as before: `OK`, with the note
  `JobSpy: <boards or none> | Workday employers: <n> | career sites: <n>`.
  LinkedIn is never listed.
- `hireember.doctor.run_checks()` and `CliRunner().invoke(app, ["doctor"])`
  complete when `SEARCH_CONFIG_PATH` holds invalid YAML (for example
  `"sites: [indeed\n"`) or a top-level list (`"- indeed\n"`). The exit code is 0,
  and the output contains a `Job sources` line with `MISSING`.

## Data and state changes
- Env var `HIREEMBER_DIR` (str path) replaces `APPLYPILOT_DIR`. `APPLYPILOT_DIR` is no longer read.
- Default data folder: `~/.hireember`. Legacy fallback to `~/.applypilot`
  applies only when `HIREEMBER_DIR` is unset and `~/.hireember` is missing. It is
  read-only resolution and nothing is migrated.
- DB file name: `hireember.db` (new folders and any `HIREEMBER_DIR` folder), or
  `applypilot.db` (legacy `~/.applypilot` fallback only). The schema does not change.
- Distribution name `hireember`; console script `hireember`. The old `applypilot` script is gone.

## Tasks
1. **Move the package to `hireember` and switch the env var.**
   - `src/applypilot/` → `src/hireember/` (`git mv`, so history follows).
   - In every `src/hireember/**/*.py` (modified), change `from applypilot` /
     `import applypilot` to `hireember`. Use
     `grep -rlE "applypilot(\.| import)" src/hireember` to find them; there are
     about 21 files.
   - `src/hireember/__main__.py` (modified): imports `hireember.cli`, and the docstring reads `python -m hireember`.
   - `pyproject.toml` (modified): `name`, `[project.scripts]` (only `hireember = "hireember.cli:app"`), wheel `packages` and `artifacts` as in the contract.
   - `src/hireember/config.py` (modified), interim: `APP_DIR = Path(os.environ.get("HIREEMBER_DIR") or Path.home() / ".hireember")`.
     This must land in the same commit as the move, because the updated
     conftest isolates through `HIREEMBER_DIR` and an older resolver would touch
     the real `~/.applypilot`.
   - `src/hireember/cli.py` (modified): `typer.Typer(name="hireember", ...)`, and the version callback prints `[bold]hireember[/bold] {__version__}`.
   - If any file under `tests/unit/` still imports `applypilot` (it is not frozen), rewrite it to `hireember` here.
   - Reinstall the venv (`uv pip install --python .venv/bin/python -e '.[dev]'`) so the `hireember` script exists. Then run lint and the tests.
2. **Legacy data-folder fallback and DB file names.** In `src/hireember/config.py` (modified):
   - Add `import sys` and `from collections.abc import Mapping`, plus the
     constants `APP_DIR_ENV = "HIREEMBER_DIR"`, `APP_DIR_NAME = ".hireember"`,
     `LEGACY_APP_DIR_NAME = ".applypilot"`, `DB_FILENAME = "hireember.db"`,
     `LEGACY_DB_FILENAME = "applypilot.db"` and `LEGACY_DIR_NOTICE`, with the
     exact text from the contract.
   - Add `resolve_app_dir(environ=None, home=None) -> tuple[Path, bool]` with the
     four-step order. A set variable means `(environ.get(APP_DIR_ENV) or "").strip()`
     is non-empty. Legacy is picked only when `(home/LEGACY_APP_DIR_NAME).is_dir()`.
   - Replace the interim line with
     `APP_DIR, USING_LEGACY_APP_DIR = resolve_app_dir()` and
     `DB_PATH = APP_DIR / (LEGACY_DB_FILENAME if USING_LEGACY_APP_DIR else DB_FILENAME)`.
   - Right after, `if USING_LEGACY_APP_DIR: sys.stderr.write(LEGACY_DIR_NOTICE + "\n")`.
     Use plain stderr and not `log`, because the CLI's `logging.basicConfig`
     would prefix a timestamp and library imports have no handler.
   - Docstrings of `load_profile`, `load_search_config` and `load_env` say
     `~/.hireember`. Add unit tests (see below).
3. **Rebrand user-facing text in the package.** Modified files:
   - `src/hireember/cli.py`: module and callback docstrings `HireEmber — AI-powered …`;
     `hireember init` and `hireember run score tailor` hints; `HireEmber Pipeline Status`; `HireEmber Doctor`.
   - `src/hireember/doctor.py`:
     - Module docstring says ``hireember doctor``.
     - Every `'applypilot init'` / `'applypilot run'` becomes `hireember`.
     - The LLM note becomes `f"Set GEMINI_API_KEY in {config.ENV_PATH} (run 'hireember init')"`, so it is right in legacy mode too.
   - `src/hireember/config.py`: the `check_tier` message `hireember init`, the `load_profile` error `hireember init`, and the module docstring `HireEmber configuration…`.
   - `src/hireember/wizard/init.py`: docstring, panel copy, generated headers
     `# HireEmber search configuration` and `# HireEmber configuration` (both
     occurrences), and the `hireember init` hints.
   - `src/hireember/view.py`: docstrings `~/.hireember/dashboard.html`, `<title>` and `<h1>` `HireEmber Dashboard`.
   - `src/hireember/pipeline.py`: docstring usage lines `hireember run …`, panel `HireEmber Pipeline`.
   - `src/hireember/apply/dashboard.py`: table title `HireEmber Dashboard`.
   - `src/hireember/discovery/jobspy.py`: docstring `HireEmber database` and the warning `hireember init`.
   - `src/hireember/llm.py`, `database.py`, `__init__.py`, `scoring/validator.py`: docstrings.
   - `src/hireember/config/searches.example.yaml`, `employers.yaml`, `sites.yaml`: header comments.
   
   Do not touch comments that credit upstream. Afterwards, `grep -rn -i applypilot src`
   may only hit the legacy constants and notice in `config.py`.
4. **Doctor survives malformed YAML.** `src/hireember/doctor.py` (modified):
   - Add `import yaml` and a private
     `_load_yaml_mapping(path: Path) -> dict`. It returns `{}` if the file is
     missing and `{}` when `yaml.safe_load` gives `None`. It raises
     `ValueError(f"top level must be a mapping, got {type(data).__name__}")`
     for a non-dict, and lets `yaml.YAMLError` and `OSError` propagate.
   - Rewrite `check_sources` to load the three sources in order:
     - search config: only if `search_cfg is None`, from `config.SEARCH_CONFIG_PATH` when it exists, else `config.CONFIG_DIR / "searches.example.yaml"`.
     - `config.CONFIG_DIR / "employers.yaml"`, then `.get("employers") or {}`.
     - `config.CONFIG_DIR / "sites.yaml"`, then `.get("sites") or []`.
     
     Each load is wrapped in `try/except (yaml.YAMLError, OSError, ValueError) as e:`, which returns `Check("Job sources", "MISSING", f"{path.name}: {e}")`. Collapse the YAML error text to one line (`" ".join(str(e).split())`).
   - A non-dict `search_cfg` argument gives `Check("Job sources", "MISSING", "searches.yaml: top level must be a mapping, got <type>")`.
   - Drop the `from hireember.discovery.workday import load_employers` import
     from doctor. Doctor now reads the same file through `config.CONFIG_DIR`,
     which can be monkeypatched; `workday.CONFIG_DIR` is bound at import and
     cannot. `workday.load_employers` itself is unchanged.
   - Add unit tests.
5. **Rebrand docs and the example env.** Modified files:
   - `README.md`:
     - Title `# HireEmber`; `pip install hireember`.
     - All command examples (Quick start, utility modes, CLI Reference, Configuration "All generated by `hireember init`").
     - "Package configs (shipped with HireEmber)".
     - License line: `HireEmber, like upstream ApplyPilot, is licensed under the [GNU Affero General Public License v3.0](LICENSE).`
     - Keep the line-3 disclaimer, the `## Fork notice` section, the PyPI and stars badges, the "What It Does" marketing copy and the "ApplyPilot vs The Alternatives" table as they are.
     - Do not write `~/.applypilot` anywhere in README.
   - `CONTRIBUTING.md`: title and intro `HireEmber`; `hireember --version`; the
     `applypilot discover` examples become `hireember discover` (a mechanical
     rename only); `--cov=src/hireember`; tree `src/hireember/`. Keep the
     upstream clone URL.
   - `.env.example`: the first two lines, as in the contract.
   - `CHANGELOG.md`: add an `## [Unreleased]` entry above `[0.2.0]`. It covers
     the rename to HireEmber and the `hireember` command; `HIREEMBER_DIR`
     replacing `APPLYPILOT_DIR`; the `~/.hireember` default and `hireember.db`;
     the read-only legacy fallback with the move command; and the doctor
     malformed-YAML fix. Historical entries are unchanged.
   - `LICENSE`: untouched.

## Implementation tests
- `tests/unit/test_app_dir.py` (new), using `resolve_app_dir(environ=..., home=tmp_path)`:
  - The env var wins, even when `.hireember` and `.applypilot` both exist.
  - Empty and whitespace values are treated as unset.
  - The `.hireember` default with an empty home.
  - Legacy is picked when only `.applypilot/` exists, and the result is `(home/".applypilot", True)`.
  - Both folders present gives `.hireember`.
  - A `.applypilot` *file* (not a dir) is not treated as legacy.
  - `APPLYPILOT_DIR` in `environ` is ignored.
  - The function creates no folders: assert the `tmp_path` listing is unchanged.
  - `LEGACY_DIR_NOTICE` has no newline and contains both paths.
  - One subprocess test, with `HOME` = tmp, only `.applypilot/`, and `HIREEMBER_DIR`
    removed: stderr has exactly one notice line, `c.DB_PATH.name == "applypilot.db"`,
    and `.hireember` is not created.
- `tests/unit/test_doctor.py` (modified):
  - `check_sources` with `config.SEARCH_CONFIG_PATH` monkeypatched to invalid YAML, then to a top-level list: status MISSING, note starts with `searches.yaml:`.
  - With `config.CONFIG_DIR` monkeypatched to a tmp dir holding a broken `employers.yaml` (and a valid `sites.yaml`): note starts with `employers.yaml:`.
  - The same with a list-valued `sites.yaml`.
  - An empty `employers.yaml` counts as zero employers, not an error.
  - A non-dict `search_cfg` argument gives MISSING.
  - `run_checks()` returns 12 checks without raising when searches.yaml is broken.
- Keep `tests/unit/test_package.py` asserting `hireember.__version__`. This is updated by the test stage; if it is not, task 1 updates it.

## Risks and rollout
- **Frozen conftest.** `tests/conftest.py` is frozen at Gate 2. The test-author
  must switch it to `HIREEMBER_DIR` and `hireember`, or no implementation can go
  green. Task 1 must flip the env var in the same commit as the move. Otherwise
  the test run could read or write the developer's real `~/.applypilot`.
- **Stale editable install.** The worktree `.venv` has
  `_editable_impl_applypilot.pth` and `applypilot-0.3.0.dist-info`. Tests use
  `PYTHONPATH=src`, so they are unaffected, but the `applypilot` console script
  will point at a missing module until someone runs
  `uv pip uninstall --python .venv/bin/python applypilot`. That is optional,
  and the install command adds `hireember`.
- **Import-time notice.** Every process that imports `hireember.config`
  (including `hireember --help`) prints the notice once in legacy mode. This is
  intended and goes only to stderr, so piping stdout stays clean.
- **DB name and HIREEMBER_DIR.** A user who sets `HIREEMBER_DIR=~/.applypilot`
  gets a new, empty `hireember.db` next to the old `applypilot.db`, as gate-1
  answer 1 says. The CHANGELOG move command includes the DB rename.
- CI (`.github/workflows/ci.yml`) and `publish.yml` have no `applypilot` paths,
  so no change is needed there.

## Open questions
- none
