# Tech spec — Harden doctor source checks and fix config and docs follow-ups from phase 0b

## Approach
Validate at the boundary. `config.resolve_jobspy_sites` (src/hireember/config.py) rejects any non-list, non-None value with `ValueError`, so a string is never iterated by character. `doctor.check_sources` (src/hireember/doctor.py) checks each nested value's type before use and returns `_bad_source`-style MISSING checks, matching the existing pattern in that function. The two discovery callers in src/hireember/discovery/jobspy.py (`search_jobs`, `_full_crawl`) catch the `ValueError`, log it, and return their existing "no sites" result shape with an error. `resolve_app_dir` uses `is_dir()` instead of `exists()`. README and CONTRIBUTING get text fixes. No new abstractions.

## Interface contract
- `hireember.config.resolve_jobspy_sites(sites: list[str] | None) -> list[str]`
  - `None` returns `list(DEFAULT_JOBSPY_SITES)`.
  - A list returns the entries with "linkedin" removed (case-insensitive) and logs a warning if any were removed, as today.
  - Any other type (str, int, dict, ...) raises `ValueError`. The message contains the phrase `must be a list` (and the word "list"), for example `JobSpy sites must be a list, got str`.
- `hireember.doctor.check_sources(search_cfg: dict | None = None) -> Check`. It never raises. It returns `Check("Job sources", "MISSING", "<file>: <problem>")` when:
  - `search_cfg["sites"]` is present, not None, and is not a list of strings (covers `5`, `"indeed"`, `{a: 1}`, and lists with non-string items). The note starts with `searches.yaml:`, contains `must be a list`, and never lists single letters of the string.
  - `employers.yaml` `employers` is not a mapping and not empty/None. The note starts with `employers.yaml:`.
  - `sites.yaml` `sites` is not a list and not empty/None, including a string. The note starts with `sites.yaml:` and contains `must be a list`.
  - Valid configs give the same result as before.
  - `search_cfg` can be passed directly (a dict), or loaded from `config.SEARCH_CONFIG_PATH` falling back to `config.CONFIG_DIR / "searches.example.yaml"`. `employers.yaml` and `sites.yaml` are read from `config.CONFIG_DIR`. Tests monkeypatch these paths.
- `hireember.config.resolve_app_dir(environ=None, home=None) -> tuple[Path, bool]`. `HIREEMBER_DIR` still wins. `<home>/.hireember` is chosen only if it is a directory. Otherwise `<home>/.applypilot` is returned as `(path, True)` if it is a directory, else `(<home>/.hireember, False)`. It stays pure (no printing); the legacy notice is printed at import by `config` via `LEGACY_DIR_NOTICE` on stderr.
- `hireember.discovery.jobspy.search_jobs(...)` and `_full_crawl(...)`, called with `sites="indeed"`, no longer raise. They return their existing no-sites result dict (`search_jobs`: has key `"error"` containing the ValueError message, `total`/`new`/`existing` = 0; `_full_crawl`: the existing keys `new, existing, errors, db_total, queries`, all zero except `db_total`, plus `"error"` with the message). `run_discovery({"sites": "indeed", ...})` likewise returns without raising.
- Docs: README.md badge image URL is `https://img.shields.io/pypi/v/hireember?color=blue` and links to `https://pypi.org/project/hireember/`. CONTRIBUTING.md contains no `hireember discover` string. The two examples become `hireember run discover`.

## Data and state changes
None.

## Tasks
1. **Reject non-list sites in `resolve_jobspy_sites` and handle it in discovery** — `src/hireember/config.py` (modified): add `if not isinstance(sites, list): raise ValueError(f"JobSpy sites must be a list, got {type(sites).__name__}")` after the None check; update the docstring and the type hint. `src/hireember/discovery/jobspy.py` (modified): in `search_jobs` and `_full_crawl`, wrap the `resolve_jobspy_sites` call in `try/except ValueError as e`, `log.error("%s", e)`, then return the existing no-sites dict with `"error": str(e)` added. In `_full_crawl` keep the `db_total` query as in the existing branch. Add unit tests (see below).
2. **Harden `check_sources`** — `src/hireember/doctor.py` (modified): before calling `resolve_jobspy_sites`, validate `search_cfg.get("sites")`: None passes through, otherwise it must be a list whose items are all `str`, else return `Check("Job sources", "MISSING", "searches.yaml: sites must be a list of strings, got <type>")`. Keep a `try/except ValueError` around the resolve call as a safety net. Check `employers` is a dict (when truthy) and return `employers.yaml: employers must be a mapping, got <type>`. Check `sites` in sites.yaml is a list (when truthy) and return `sites.yaml: sites must be a list, got <type>`. Falsy values (None, empty) still count as empty, as before. Add tests.
3. **`resolve_app_dir` requires a directory** — `src/hireember/config.py` (modified): change `current.exists()` to `current.is_dir()`; adjust the docstring ("if it is a directory"). Add tests.
4. **Fix README badge and CONTRIBUTING commands** — `README.md` (modified): line 13 badge image and link use `hireember`. `CONTRIBUTING.md` (modified): lines 48 and 69 use `hireember run discover`, with a short note that it runs the discovery stage over the configured sources. Verify with `hireember run --help` that `discover` is a valid stage, and grep CONTRIBUTING for other nonexistent `hireember` commands.

## Implementation tests
Add to the existing test files for config and doctor (find them under `tests/`, following their conventions: isolation via `HIREEMBER_DIR`, monkeypatched `config.CONFIG_DIR`, `config.SEARCH_CONFIG_PATH`):
- `resolve_jobspy_sites("indeed")`, `5` and `{}` raise `ValueError` mentioning "list". `None` and a list with "linkedin" behave as before.
- `check_sources` for `sites: 5`, `indeed`, `{a: 1}` and `["indeed", 3]`: MISSING, note names searches.yaml, contains no letter-by-letter list. The same for `employers: 5` and sites.yaml `sites: 5` / `sites: foo`. A valid config is unchanged.
- `search_jobs(..., sites="indeed")` and `_full_crawl` return an error dict without raising (use a temp DB via `HIREEMBER_DIR`; no network, because the failure occurs before the scrape).
- `resolve_app_dir(environ={}, home=tmp)` with a `.hireember` file and `.applypilot` directory returns `(.applypilot, True)`. Existing `.hireember` directory returns `(.hireember, False)`. Neither gives `(.hireember, False)`.
- A docs test: README contains `pypi.org/project/hireember` and not `applypilot` in the badge line. CONTRIBUTING does not contain `hireember discover`.

## Risks and rollout
Low. `resolve_jobspy_sites` now raises for non-list inputs. Its only callers are the three sites above and all are handled. An empty `.hireember` file in `$HOME` previously blocked the legacy fallback. That is the intended fix.

## Open questions
- none
