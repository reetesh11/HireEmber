# Interface contract — phase-0-foundation

All Python imports assume `PYTHONPATH=src` (package `applypilot`). Tests must never touch the real `~/.applypilot` or the network.

### Test harness (written with the acceptance tests; frozen at Gate 2)
The acceptance-test stage owns these files. The implementer does not create or edit them.
- `tests/conftest.py` (shared, required by AC-1). Before any `applypilot` import, at module top level, it must set `os.environ["APPLYPILOT_DIR"]` to a fresh temporary directory, and it must remove `CHROME_PATH` from the environment. `applypilot.config` reads `APPLYPILOT_DIR` once, at import time, to build `APP_DIR`, `DB_PATH`, `PROFILE_PATH` and the other paths. It must also provide a fixture `fixture_form_server`, which yields the base URL `http://127.0.0.1:<port>/` of a stdlib `http.server.ThreadingHTTPServer` bound to `127.0.0.1` on an ephemeral port and serving `tests/fixtures/`. The fixture shuts the server down afterwards.
- `tests/fixtures/forms/basic_form.html`. It is served at `<base>/forms/basic_form.html` and contains a `<form>` with at least one `<input type="text">`, one `<input type="file">` and one submit button (`<button type="submit">` or `<input type="submit">`). It has no external resources.
- Acceptance tests live in `tests/acceptance/`. Implementer unit tests live in `tests/unit/`.
- Test runner: `PYTHONPATH=src python -m pytest tests/` (pytest is at least 7.4; `pyproject.toml` sets `testpaths = ["tests"]` and `pythonpath = ["src"]`).
- When a test needs the default DB, monkeypatch `applypilot.database.DB_PATH` (used by `get_connection()` / `init_db()` with no argument) and `applypilot.config.DB_PATH` (used by doctor) to a `tmp_path` file.

### `applypilot.config` (LinkedIn policy)
- `DEFAULT_JOBSPY_SITES: tuple[str, ...] = ("indeed", "zip_recruiter")`.
- `is_linkedin_url(url: str | None) -> bool`. True if and only if the URL's host, lower-cased, is `linkedin.com` or ends with `.linkedin.com`. A URL without a scheme (`www.linkedin.com/jobs/view/1`) is parsed as `https://`. `None`, `""` and `"nan"` give False. `https://notlinkedin.com/x` and `https://example.com/?ref=linkedin.com` give False.
- `resolve_jobspy_sites(sites: list[str] | None) -> list[str]`. `None` returns `list(DEFAULT_JOBSPY_SITES)`. Otherwise it returns the given list in its original order, minus every entry whose `.strip().lower() == "linkedin"`. When it removes something, it logs a WARNING containing `LinkedIn` through the logger `applypilot.config`. It can return `[]`.
- `class LinkedInBlockedError(ValueError)`. `str(err)` contains `LinkedIn` and the offending URL.

### `applypilot.discovery.jobspy`
- The module imports even when `python-jobspy` is not installed. The module attribute `scrape_jobs` is what every search calls, so tests can monkeypatch `applypilot.discovery.jobspy.scrape_jobs`. When the package is missing, calling the fallback raises `ImportError` with an install hint.
- `search_jobs(query: str, location: str, sites: list[str] | None = None, remote_only: bool = False, results_per_site: int = 50, hours_old: int = 72, proxy: str | None = None, country_indeed: str = "usa") -> dict`. It calls `scrape_jobs(**kwargs)` once, with `kwargs["site_name"] == resolve_jobspy_sites(sites)`, so with `sites=None` that is `["indeed", "zip_recruiter"]`. `linkedin_fetch_description` is never passed. If the resolved list is empty, it does not call `scrape_jobs` and returns `{"error": "no JobSpy sites configured", "total": 0, "new": 0, "existing": 0}`. If `scrape_jobs` returns an empty DataFrame, it returns `{"total": 0, "new": 0, "existing": 0}` without touching the DB.
- `_full_crawl(search_cfg: dict, tiers=None, locations=None, sites: list[str] | None = None, results_per_site=100, hours_old=72, proxy=None, max_retries=2) -> dict`. Every `scrape_jobs` call gets a `site_name` list with no `linkedin`; with `sites=None` that is `["indeed", "zip_recruiter"]`. Glassdoor is still split into its own call, as today. `search_cfg` needs `queries: [{query, tier}]` and `locations: [{location, remote, label?}]`. It calls `init_db()` on the default DB path. If the resolved list is empty, it returns `{"new": 0, "existing": 0, "errors": 0, "db_total": <count>, "queries": 0}` without scraping.
- `run_discovery(cfg: dict | None = None) -> dict`. Unchanged; it reads `cfg["sites"]`, which goes through the same resolution.
- `store_jobspy_results(conn: sqlite3.Connection, df: pandas.DataFrame, source_label: str) -> tuple[int, int]`. It returns `(new, existing)`. A row whose `job_url` or `job_url_direct` is a LinkedIn URL is not inserted and is not counted. Columns used: `job_url`, `job_url_direct`, `title`, `company`, `location`, `site`, `description`, `min_amount`, `max_amount`, `interval`, `currency`, `is_remote`. Missing columns are fine. Example: rows with `job_url` set to `https://www.linkedin.com/jobs/view/123`, `https://linkedin.com/jobs/view/456` and `https://www.indeed.com/viewjob?jk=1` give `(1, 0)`, and only the Indeed URL is in `jobs`. Use `conn = applypilot.database.init_db(tmp_path / "t.db")`.

### Other discovery store paths (same rule: LinkedIn rows skipped, not counted)
- `applypilot.database.store_jobs(conn, jobs: list[dict], site: str, strategy: str) -> tuple[int, int]` skips a job whose `url` or `application_url` is LinkedIn.
- `applypilot.discovery.workday.store_results(conn, jobs, employers) -> tuple[int, int]` skips a job whose resolved URL is LinkedIn.

### `src/applypilot/config/searches.example.yaml`
- `boards:` does not contain `linkedin`; it keeps `indeed`, `glassdoor`, `zip_recruiter` and `google`. No other key in the file lists `linkedin`.

### Apply stage (`applypilot.apply.launcher`)
- `main(limit=1, target_url=None, min_score=7, headless=False, model="sonnet", dry_run=False, continuous=False, poll_interval=60, workers=1) -> None`. When `is_linkedin_url(target_url)` is true, it raises `applypilot.config.LinkedInBlockedError` as its first statement, before `ensure_dirs`, signal handlers, the dashboard, `launch_chrome` or `subprocess.Popen`.
- `gen_prompt(target_url: str, min_score: int = 7, model: str = "sonnet", worker_id: int = 0)` raises `LinkedInBlockedError` for a LinkedIn `target_url` before touching the DB.
- `worker_loop(worker_id: int = 0, limit: int = 1, target_url: str | None = None, min_score: int = 7, headless: bool = False, model: str = "sonnet", dry_run: bool = False) -> tuple[int, int]`. After `acquire_job` returns a job whose `url` or `application_url` is LinkedIn:
  - It does not call `launch_chrome` or `run_job`.
  - It updates the job row to `apply_status = 'failed'`, `apply_error = 'linkedin_blocked: LinkedIn jobs are not supported'` and `apply_attempts = 99`.
  - It logs a WARNING containing `LinkedIn`.
  - It does not count the job in the returned `(applied, failed)`, and it moves on to the next job. In `target_url` mode it stops instead.

  With a queue holding only that job and `limit=1`, it returns `(0, 0)`. Queue-mode `acquire_job` needs a `jobs` row with `tailored_resume_path` not null, `apply_status` null, `fit_score` at least `min_score`, and `site` not in the `sites.yaml` blocked list (for example `site='indeed'`). Use the default DB via the monkeypatched `applypilot.database.DB_PATH`, and call `applypilot.apply.dashboard.init_worker(0)` first. Stub points: `applypilot.apply.launcher.launch_chrome`, `applypilot.apply.launcher.run_job` and `applypilot.apply.launcher.subprocess.Popen`.

### CLI (`from applypilot.cli import app`; test with `typer.testing.CliRunner`)
- `applypilot apply --url https://www.linkedin.com/jobs/view/123` (with or without `--gen`) exits with code 1 and prints `LinkedIn job URLs are not supported: <url>`. The check runs before `_bootstrap()`, the tier check, the DB, Chrome and Claude Code.
- `applypilot doctor` exits with code 0. It prints a title line `ApplyPilot Doctor`, then one line per check in the form `  <name><padding><STATUS>  <note>`. Each check is printed on exactly one line (`soft_wrap=True`), so the name and its status are always on the same line. The status words are `OK`, `MISSING`, `WARN` and `optional`. The check names, in order:
  `Python`, `profile.json`, `resume.txt`, `searches.yaml`, `python-jobspy`, `LLM API key`, `Claude Code CLI`, `Chrome/Chromium`, `Node.js`, `Database`, `Job sources`, `CapSolver API key`. A tier summary line follows the checks, as today.

### `applypilot.doctor` (new)
- `@dataclass(frozen=True) class Check: name: str; status: str; note: str`. `status` is one of `"OK"`, `"MISSING"`, `"WARN"`, `"optional"`.
- `check_python(version: tuple[int, int, int] | None = None) -> Check`. It defaults to `sys.version_info[:3]`. The name is `Python`. At 3.11 or later the status is `OK` and the note is the version (`3.12.4`). Below that the status is `MISSING` and the note is `found 3.10.0, need 3.11+`.
- `check_chrome() -> Check`. The name is `Chrome/Chromium`. It calls `applypilot.config.get_chrome_path()`, looked up at call time, so monkeypatching `applypilot.config.get_chrome_path` takes effect. On success the status is `OK` and the note is the path. On `FileNotFoundError` the status is `MISSING` and the note mentions `CHROME_PATH`.
- `get_node_version() -> tuple[int, int, int] | None`. It runs `node --version` when `shutil.which("node")` finds Node (5 s timeout) and parses `vX.Y.Z`. It returns None when Node is absent or the output cannot be parsed.
- `check_node() -> Check`. The name is `Node.js`. It calls the module-level `get_node_version()` at call time, so monkeypatching `applypilot.doctor.get_node_version` takes effect. Version 18 or later gives `OK` with a note like `v20.11.1`. Below 18 gives `MISSING` with a note like `found v16.20.0, need 18+`. None gives `MISSING` with a note mentioning `Node.js 18+`. With `PATH=""` it reports `MISSING`.
- `check_claude() -> Check`. The name is `Claude Code CLI`. If `shutil.which("claude")` finds it, the status is `OK`; otherwise `MISSING`.
- `check_database(db_path: str | Path | None = None) -> Check`. The name is `Database`. It defaults to `applypilot.config.DB_PATH`, read at call time. If the file is absent the status is `MISSING` and the note mentions `applypilot init`. If the file opens read-only and `SELECT count(*) FROM sqlite_master` succeeds, the status is `OK` and the note is the path. Otherwise the status is `MISSING` with the error. It never creates the file.
- `check_sources(search_cfg: dict | None = None) -> Check`. The name is `Job sources`. `None` loads `config.load_search_config()`. The note lists the JobSpy boards from `resolve_jobspy_sites(search_cfg.get("sites"))`, the Workday employer count and the career-site count (`config.load_sites_config()["sites"]`), for example `JobSpy: indeed, zip_recruiter | Workday employers: 48 | career sites: 30`. The status is `OK` if there is at least one source in total; otherwise `MISSING`. The note never contains `linkedin`.
- `run_checks() -> list[Check]` returns all twelve checks in the CLI order above.

### CI and repo files (static content tests may read)
- `.github/workflows/ci.yml`. `on:` has `push`, `pull_request` and `workflow_dispatch`. The job matrix is `python-version: ["3.11", "3.12", "3.13"]`. One step runs `ruff check .`, another runs `python -m pytest tests/` (with `PYTHONPATH: src`). The file contains no `continue-on-error` and no `|| true`.
- `pyproject.toml`. `[project.optional-dependencies] dev` includes `pytest` and `ruff`.
- `README.md` has a section headed `## Fork notice`. It contains the words `fork`, `ApplyPilot`, the link `https://github.com/Pickle-Pixel/ApplyPilot` and `AGPL-3.0`. The existing `## License` section and the Pickle-Pixel attribution stay.
- `docs/traceability.md` has a Markdown table with the header `| Requirement | Description | Tests |` and one row each for `FR-DIS-2`, `SAF-4`, `FR-CLI-2`, `NFR-1`, `NFR-10` and `NFR-11`. Each row's Tests cell names at least one path under `tests/` (or a `path::test_name`). The NFR-1 and NFR-11 rows also name `.github/workflows/ci.yml`.
