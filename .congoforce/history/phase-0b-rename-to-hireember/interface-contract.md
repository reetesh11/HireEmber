# Interface contract — phase-0b-rename-to-hireember

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
