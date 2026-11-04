# Interface contract — phase-9-search-precision

### `hireember.titles` (new, `src/hireember/titles.py`)
- `title_filter(title: str | None, include: Sequence | None, exclude: Sequence | None) -> str | None`
  - Returns `None` (keep) or a reason string.
  - Exclude is checked first: a match returns `"title: <matched exclude entry, stripped, as written>"`, for example `"title: program manager"`.
  - Then, if `include` has at least one usable entry and nothing matches, returns `"title: not in target roles"`. A `None` or empty title with a non-empty include list returns that same reason.
  - Matching is case-insensitive on whole words or whole phrases. Any run of non-alphanumeric characters (spaces, hyphens, slashes, punctuation) counts as a single word boundary on both the title and the entry. So `sales` matches "Sales/Marketing Lead" and "Sales Engineer" but not "Salesforce Developer"; `program manager` matches "Senior  Program   Manager"; entry `TS/SCI` matches "TS-SCI Engineer".
  - Entries that are not `str`, or are blank after stripping, are ignored. Both lists empty (or all unusable) returns `None`.
- `propose_title_lists(roles: Sequence[str], target_role: str = "", resume_text: str = "") -> tuple[list[str], list[str]]`
  - Returns `(include, exclude)`, lower-case, de-duplicated, order stable.
  - `include`: the given roles and `target_role`, plus, when any of them (or the resume text) is software-ish (contains engineer, developer, programmer or software), the entries `software engineer`, `engineer`, `developer`.
  - `exclude`: for software-ish input, a fixed non-engineering list that contains at least `sales`, `program manager`, `account executive`, `recruiter`, `marketing`, `customer success`, `business development`; empty otherwise.

### `hireember.search_config` (new, `src/hireember/search_config.py`)
Paths are read from `hireember.config.SEARCH_CONFIG_PATH` and `hireember.config.PROFILE_PATH` at call time (no caching, so a saved value is seen on the next call).
- `load() -> dict`: parsed `searches.yaml`, `{}` when missing, unreadable or not a mapping. No fallback to the example file.
- `title_lists(cfg: dict) -> tuple[list[str], list[str]]`: `(title_include, title_exclude)`. `title_exclude` is used when the key is present, otherwise `exclude_titles`. Non-string items dropped.
- `location_lists(cfg: dict) -> tuple[list[str], list[str]]`: `(accept, reject)`. `location.accept_patterns` wins when it is a list, otherwise `location_accept`; `location.reject_patterns` wins when it is a list, otherwise `location_reject_non_remote`. Both styles present: the new block wins (no union).
- `KNOWN_KEYS: frozenset[str]`: top-level keys some code reads: `queries, locations, location, location_labels, tiers, proxy, sites, defaults, glassdoor_location_map, workday_max_tier, workday_location_filter, title_include, title_exclude, exclude_titles, location_accept, location_reject_non_remote`.
- `class SettingsError(ValueError)`: attribute `field: str | None`; `str(exc)` is the user message.
- `class UnreadableConfigError(Exception)`: `str(exc)` is `"Could not read searches.yaml: <parse error>"` (or `profile.json`).
- `read_settings() -> dict`: returns exactly
  `{"title_include": [..], "title_exclude": [..], "location_accept": [..], "location_reject": [..], "remote": bool, "personal": {"city": str, "province_state": str, "country": str}}`.
  Aliases and old keys are normalised. `remote` is true when any `locations[]` entry has a truthy `remote`. Missing files give empty lists, `remote` false, empty strings. Malformed YAML/JSON raises `UnreadableConfigError`.
- `save_settings(payload: dict) -> dict`: validates, writes, returns `read_settings()`.
  - Payload has the same shape as `read_settings()`; absent keys are left unchanged.
  - Writes only: `title_include`, `title_exclude` (and deletes `exclude_titles`), `location.accept_patterns` (and deletes `location_accept`), `location.reject_patterns` (and deletes `location_reject_non_remote`), the `remote` flag on `locations[]` entries, and `personal.city`, `personal.province_state`, `personal.country` in `profile.json`. Every other key in both files is kept. Remote true with no remote entry appends `{"location": "Remote", "remote": true}`; remote false sets `remote: false` on every entry.
  - `searches.yaml` is dumped with `yaml.safe_dump(sort_keys=False, allow_unicode=True)`; comments are lost. A missing file is created with only the saved keys; a missing `profile.json` is created as `{"personal": {...}}`.
  - Validation (raises `SettingsError`, nothing written): non-string entry `"Enter text."`; blank or whitespace entry `"Enter a keyword."`; duplicate after case folding `"'<term>' is already in the list."` (`<term>` is the later duplicate as entered, stripped); entry over 80 characters `"Keep entries under 80 characters."`; a list field that is not a list `"Enter a list of keywords."`; `remote` not a bool `"remote must be true or false."`; a personal value that is not a string `"Enter text."` or over 80 characters `"Keep entries under 80 characters."` (blank personal values are allowed). Entries are stored stripped. `SettingsError.field` is the payload key (`"title_include"`, `"personal.city"`, ...).
  - Atomic: both new contents are written to temp files in the target folders first; then `os.replace` on `searches.yaml`, then `profile.json`; if the second replace fails the first file is restored to its original bytes and the error propagates. A failure leaves both files byte-identical. Files whose content did not change are not rewritten.
  - Refuses to write (raises `UnreadableConfigError`) when either existing file is malformed.

### `hireember.location` (changed)
- `location_skip_reason(location, profile=None, search_cfg=None) -> str | None`: signature unchanged. Accept/reject lists now come from `search_config.location_lists(cfg)`; the `locations[].location` entries and `profile["personal"]` city/province_state/country are still added to accept targets. `profile=None` still means no personal fields (callers pass `config.load_profile()`), so a changed `personal.country` is seen on the next call that passes the re-read profile. With `search_cfg=None` the file is re-read on each call.
- Old-key and new-key configs give identical results; `CA` never matches "Chicago, IL" or "Vacation" and matches "Toronto, CA" and "Oakland, CA"; `SF` does not match "Transfer" and matches "SF Bay Area"; "Calgary, AB" passes for target Canada. Remote, empty and placeholder locations pass as before.
- No `_location_ok` exists in `discovery/jobspy.py`, `discovery/workday.py` or `discovery/smartextract.py`, and no other location matcher is under `discovery/`.

### `hireember.intake` (new, `src/hireember/intake.py`)
- `class DropTally`: `counts: dict[str, int]` (keys `"title"`, `"location"`, both start 0); `items: list[tuple[str, str]]` of `(job title, reason)`; `add(title, reason)` (type is the reason prefix before `:`); `total -> int`; `summary_line() -> str` is `"Dropped 34: 21 title, 13 location"`; `hint(kept: int = 1) -> str` is `""` when `total == 0`, else `"<summary_line>. Review them in Tickets (skipped) or edit rules in Profile."`, plus `" Check your target roles and locations in Profile."` when `kept == 0`.
- `class JobFilter`: `JobFilter.load(search_cfg: dict | None = None, profile: dict | None = None) -> JobFilter` (reads `searches.yaml` and `profile.json` fresh when arguments are `None`; a missing profile is `{}`); `reason(title: str | None, location: str | None) -> str | None` returns `title_filter(...)` first, then `location_skip_reason(...)`.
- `mark_dropped(conn, url: str, reason: str, title: str | None, tally: DropTally | None = None) -> None`: sets `jobs.detail_scraped_at` (when NULL), opens a `skipped` ticket with `reason` via `tickets.open_ticket`, adds to the tally.
- `store_filtered(conn, jobs: list[dict], *, site: str, strategy: str, flt: JobFilter | None = None, tally: DropTally | None = None, now: str | None = None) -> tuple[int, int, int]`: `(new_kept, existing, dropped)`. Each new job that `flt.reason(...)` rejects is inserted and marked dropped; jobs already in `jobs` count as `existing` and are never re-filtered. `flt=None` loads a fresh `JobFilter`.
- `write_run_log(conn, run_id: int | None, tally: DropTally) -> None`: no-op when `tally.total == 0` or `run_id is None`. Otherwise `runs.log_event(..., source="discover", level="info")` for one summary line `Dropped 34: 21 title, 13 location`, then up to 20 lines `dropped: <job title> (<reason>)`, then `...and N more` when over 20. Readable with `runs.get_run_log(conn, run_id)`.

### Discovery results (changed)
- `discovery.companies.discover_companies(conn, *, adapters=None, run_id=None, now=None) -> dict`: adds `"dropped": {"title": int, "location": int}` (always present, zeros when none) and `"hint": str` (see `DropTally.hint`, `kept` is the number of kept roles). `new` counts kept new jobs only; `found = new + existing + dropped`. `message` is unchanged. The run log lines are written through `write_run_log`. Workday responses and careers-page jobs both go through this path, so each is filtered before insert.
- `discovery.jobspy.store_jobspy_results(conn, df, source_label, flt: JobFilter | None = None, tally: DropTally | None = None) -> tuple[int, int]`: with a filter, rejected rows are stored and marked dropped; `(new, existing)` count kept new and existing rows. `run_discovery()` result gains `"dropped"` and `"hint"`. The `filtered` result key is removed.
- `discovery.workday.run_workday_discovery(...)` and `discovery.smartextract.run_smart_extract(...)` store through `store_filtered`; their result dicts gain `"dropped"` and `"hint"`. `workday.search_employer` and `scrape_employers` no longer take `location_filter`, `accept_locs` or `reject_locs`.

### Tickets and restore (changed)
- `hireember.tickets`:
  - `RESTORED_REASON = "restored from filter"`.
  - `class NotRestorableError(TicketError)` with message `"Only jobs dropped by the title or location filter can be restored."`.
  - `is_dropped_reason(reason: str | None) -> bool`: true when the reason starts with `title:` or `location:`.
  - `restore_dropped(conn, ticket_id: int) -> dict`: for a `skipped` ticket with a dropped reason, sets status `pending` with reason `RESTORED_REASON` (actor `user`), clears `jobs.detail_scraped_at` when `jobs.full_description` is NULL, and returns `get_ticket(...)`. Any other ticket (including an already restored one) raises `NotRestorableError`; an unknown id raises `TicketNotFoundError`.
  - `is_restored(conn, ticket_id: int) -> bool`.
- HTTP `POST /api/tickets/<id>/restore` (empty or `{}` body): `200` with the ticket detail JSON (the same object `GET /api/tickets/<id>` returns, so `status == "pending"` and `status_reason == "restored from filter"`); `409 {"error": "Only jobs dropped by the title or location filter can be restored.", "code": "not_restorable"}`; `404 {"error": "Ticket <id> not found.", "code": "not_found"}`.
- After restore, `hireember.gating.score_job_for_ticket` does not re-apply the location check to that ticket, and after scoring applies the threshold (`pending` or `skipped` with the usual reasons) to an unscored `pending` ticket as it already does for `blocked for human`.
- `GET /api/tickets` gains the query parameter `status=<one of ALLOWED_STATUSES>`. Without it, tickets that are `skipped` with a `title:` or `location:` reason are left out of the list and of `counts`; with `status=skipped` they are included. An unknown status returns `400` in the existing `bad_filter` error shape.
- `database.get_stats(...)` gains `"title_skipped"` (skipped tickets with reason `title:%`), alongside the existing `"location_skipped"`. `hireember stats` prints a "Skipped by title" row.

### Runs (changed)
- `runs.RunSummary` gains `dropped_title: int = 0` and `dropped_location: int = 0` (defaulted, appended last).
- `execute_run` stores the discover result's `dropped` counts in new `runs` columns `dropped_title`, `dropped_location`.
- `runs._stage_result("discover", ...)` message: unchanged text, followed by ` ` and the `hint` when `dropped` has any count.
- `GET /runs?fragment=1` (and `/runs`): the table gains a column with header `Dropped`. For a run with dropped jobs the cell reads `Dropped 34 (21 title, 13 location)`; it is empty for runs with none or from before this change.

### Profile API (new, in `web/server.py`)
- `GET /api/profile` → `200` with `read_settings()` JSON. Unreadable file → `422 {"error": "Could not read searches.yaml: <parse error>", "code": "unreadable"}`.
- `PUT /api/profile` with a JSON object → `200` with the re-read settings JSON. `SettingsError` → `400 {"error": "<message>", "code": "bad_request", "field": "<field>"}`; unreadable file → `422` as above; any other write failure → `500 {"error": "Could not save: <reason>. Nothing was changed.", "code": "save_failed"}` with both files unchanged. Host and origin guards behave as for other write routes.

### Scorer (changed)
- `scoring.scorer.score_job(resume_text, job, profile=None, resume_context="") -> dict`: signature unchanged. When `search_config.title_lists(search_config.load())[0]` is non-empty, the messages sent to `get_client("fast").chat(...)` contain the include terms as a role family line (`Target role family: a, b`) in the user message and a system rule that a job outside the family scores 1-3 with the word "role family" in the reasoning. When the response reasoning contains "role family" (case-insensitive) and the include list is non-empty, the returned `score` is capped at 3. With `title_include` empty, no role-family line or rule is added and no cap applies. `SCORE_PROMPT` itself is unchanged.

### Init (changed)
- `wizard.init._setup_searches(ask=None, out=None)`: signature unchanged. The written `searches.yaml` contains `title_include:` and `title_exclude:` lists from `titles.propose_title_lists(roles, profile experience.target_role, resume text)`. If `searches.yaml` already has a non-empty list under `title_include` or `title_exclude` (or the `exclude_titles` alias), that list is kept as is. The final init output includes the line `Proposed target roles and hard-no titles. Edit them in the dashboard Profile tab.`

### Doctor (changed)
- `doctor.check_search_config_keys(cfg: dict | None = None) -> list[Check]`; `cfg=None` loads `searches.yaml` (a missing file gives `[]`). Added to `run_checks()` output.
  - Unknown top-level key: `Check("searches.yaml", "WARN", "Unknown config key 'exclude_title' in searches.yaml (not read by any code). Did you mean 'title_exclude'?")`; the "Did you mean" sentence is omitted when no close match exists. Matching: compare keys with underscore-split tokens sorted and a trailing `s` stripped (so `exclude_title` suggests the canonical `title_exclude`), then `difflib.get_close_matches` with cutoff 0.8 against `title_include, title_exclude, location, locations, queries`.
  - Non-empty `queries` and both title lists empty (after aliasing): `Check("searches.yaml", "WARN", "Job-board queries are set but title_include and title_exclude are both empty; discovery will keep every title.")`.
  - A clean config returns `[]`.

### Dashboard UI (`src/hireember/web/static/index.html`)
- New tab button `role="tab"` with id `tab-profile`, text `Profile`, section `#page-profile`; `?tab=profile` selects it.
- Text and controls: `Loading profile...` while loading; `Could not load profile.` plus a `Retry` button on failure; read-error message `Could not read searches.yaml: <parse error>` with Save disabled. Section headings `Target roles`, `Hard-no titles`, `Target locations`, `Rejected locations`, `Where I live`. Helper texts exactly as in the product spec, including the matching hint `Matches whole words or phrases, ignoring case. 'sales' matches 'Sales Engineer' but not 'Salesforce Developer'.`
- Each keyword section: an input (ids `p-title_include`, `p-title_exclude`, `p-location_accept`, `p-location_reject`), a button `Add`, chips with a button labelled `Remove <term>`; Enter in the input adds. Checkbox labelled `Remote jobs accepted` (id `p-remote`). Text fields labelled `City`, `Region/State/Province`, `Country` (ids `p-city`, `p-province_state`, `p-country`). Button `Save` (disabled until something changes). Inline errors next to the field use the `SettingsError` messages. Status line `Saved. The next discover run will use these values.` on success; `Could not save: <reason>. Nothing was changed.` on failure. Nothing is sent until Save.
- Tickets: rows (list view and card detail) of skipped tickets whose `status_reason` starts with `title:` or `location:` show a button `Restore`; click calls `POST /api/tickets/<id>/restore` and the row leaves the skipped list. No `Restore` button on other tickets. A status filter `<select id="f-status">` (label `Status`, first option `All except dropped`, then each status) maps to `?status=`.
