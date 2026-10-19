# Interface contract — phase-0c-doctor-followups

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
