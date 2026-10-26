# Interface contract — phase-5-scheduler-companies

All paths are under `src/hireember/`. "conn" is a `sqlite3.Connection` from `hireember.database.get_connection()` / `init_db()`. Timestamps stored in the DB are ISO-8601 UTC strings, as elsewhere.

### `hireember.runs`
- `class RunInProgressError(Exception)`: `str(e) == "A run is already in progress."`.
- `@dataclass Stages`: fields `discover`, `enrich`, `score`, `tailor`, `apply`, all required callables.
  - `discover(conn, run_id: int) -> dict` with keys `found: int`, `new: int`.
  - `enrich(conn, run_id: int) -> dict` (result ignored).
  - `score(conn, run_id: int) -> dict` with keys `scored: int`, `skipped: int`.
  - `tailor(conn, run_id: int) -> dict` with keys `created: int`, `blocked: int`.
  - `apply(conn, run_id: int, limit: int) -> dict` with key `submitted: int`.
  - A missing key counts as 0.
- `@dataclass RunSummary`: `id: int`, `kind: str` (`"full"`), `trigger: str` (`"scheduled"` or `"manual"`), `status: str` (`"running"`, `"completed"`, `"partial"` when a stage raised, `"interrupted"`), `started_at: str`, `ended_at: str | None`, `found: int`, `scored: int`, `skipped: int`, `tickets_created: int`, `tickets_blocked: int`.
- `execute_run(trigger: str = "manual", *, stages: Stages | None = None, apply: bool = False, apply_limit: int | None = None, conn=None, now: datetime | None = None) -> RunSummary`
  - Takes the run lock; if held by a live process, raises `RunInProgressError` and writes no row.
  - Inserts one `runs` row (`status="running"`), then calls `discover`, `enrich`, `score`, `tailor` in that order. Calls `apply(conn, run_id, limit)` only if `apply` is true and `limit > 0`; `limit = apply_limit` if given, otherwise 25. When `apply` is false, `stages.apply` is never called.
  - A stage that raises is logged to the run log with `source` = the stage name, the run continues with the next stage, and the final status is `"partial"`.
  - Counts: `found` = `discover["found"]`; `scored`, `skipped` = `score[...]`; `tickets_created` = number of `tickets` rows with `created_at >= started_at`; `tickets_blocked` = number of queue items added by `enqueue_blocked` at the end of this run. Finishes the same row (`ended_at`, status, counts), releases the lock in `finally`, and returns the summary.
  - `now` is the run's start time (default: current UTC time).
- `run_stage(stage: str, *, stages: Stages | None = None, conn=None, limit: int | None = None, min_score: int | None = None, validation_mode: str = "normal") -> StageResult`
  - `stage` in `("discover", "score", "tailor", "apply")`, else `ValueError`.
  - Takes the same lock (raises `RunInProgressError`), calls only that stage callable, writes **no** `runs` row, calls `enqueue_blocked` after score, tailor and apply, and stores the result (JSON) in setting `last_stage_result`.
  - `StageResult(stage: str, message: str, counts: dict)`; `message` is exactly one of `"discover: {found} roles found, {new} new."`, `"score: {scored} scored, {skipped} skipped."`, `"tailor: {created} tickets created, {blocked} blocked."`, `"apply: {submitted} submitted."`. `limit` is passed to apply (default 1).
- `start_stage_async(stage: str, *, stages=None, limit=None, min_score=None) -> threading.Thread`: acquires the lock synchronously (raises `RunInProgressError`), then runs the stage in a daemon thread that owns the lock.
- `enqueue_blocked(conn) -> int`: for each ticket with status `"blocked for human"` that has no open queue item (`resolved_at IS NULL`), inserts a `queue_items` row (`ticket_id`, `kind="run blocked"`, `reason` = ticket `status_reason` or `"Needs your attention"`, `page_link` = job `application_url`, else job `url`); returns the number inserted. `answers.list_queue` then shows company, reason and page link, all non-empty.
- `log_event(conn, run_id: int | None, source: str, message: str, level: str = "error") -> None`; `get_run_log(conn, run_id: int) -> list[dict]` with keys `time, source, level, message`, oldest first.
- `list_runs(conn, limit: int = 50) -> list[RunSummary]`, newest first. `get_run(conn, run_id) -> RunSummary | None`.
- `is_pid_alive(pid: int) -> bool` (module-level, patchable). A lock whose pid is not alive, or older than 24 hours, is stale: it is reclaimed and any `runs` row still `"running"` is set to `"interrupted"`.

### `hireember.companies`
- `ATS_TYPES = ("workday", "careers-page")`.
- Errors (all subclass `TicketError` from `hireember.tickets`): `CompanyExistsError(name)`, `CompanyMissingError(name)`, `UnknownAtsError(value)` (message `Unknown ATS type "<x>". Valid types: workday, careers-page.`).
- `add_company(conn, name: str, careers_url: str, ats_type: str) -> int`: duplicate name (case-insensitive, among active companies) raises `CompanyExistsError`; an inactive row of that name is reactivated with the new URL/type. Returns the company id.
- `remove_company(conn, name: str) -> None`: sets `active = 0`; unknown or already removed raises `CompanyMissingError`.
- `search_list(conn) -> list[dict]`: active companies with non-empty `careers_url` and `ats_type`; keys `id, name, careers_url, ats_type`.
- `tickets.list_companies(conn)` (modified, additive): returns only active companies; each dict also has `careers_url` and `ats_type` (`""` when unset).

### `hireember.discovery.companies`
- `discover_companies(conn, *, adapters: dict[str, Callable[[dict], list[dict]]] | None = None, run_id: int | None = None, now: datetime | None = None) -> dict`
  - Iterates `companies.search_list(conn)`. For each, calls `adapters[ats_type](company)` where `company` has keys `id, name, careers_url, ats_type`; the adapter returns role dicts with keys `title, url`, and optionally `location, salary, description`. Default adapters: `{"workday": ..., "careers-page": ...}`.
  - Stores roles with `database.store_jobs(conn, roles, site=<company name>, strategy=<ats_type>, now=...)` after setting `company` = company name on each role. The role's source is the company name; date found is `jobs.discovered_at`, kept on re-discovery; `jobs.last_seen_at` is refreshed.
  - An adapter that raises (or a `careers-page` result whose status is not PASS/PARTIAL/FAIL) is logged with `runs.log_event(conn, run_id, source=<company name>, message=<error text>)`, and the loop continues.
  - Returns `{"found": int, "new": int, "existing": int, "companies": int, "failures": [{"source": str, "error": str}], "message": str}`. With an empty list: `found == 0` and `message == "No companies to search. Add one with `hireember company add`."`.
- `hireember.database.store_jobs(conn, jobs, site, strategy, now: str | None = None)` gains the optional `now` (ISO string); behaviour is unchanged when omitted.

### `hireember.scheduler`
- `class ScheduleError(ValueError)`: the message is exactly `Invalid time "<value>". Use 24-hour HH:MM, e.g. 08:00.`
- `parse_time(value: str) -> str`: returns zero-padded `"HH:MM"` for `00:00`..`23:59`; else raises `ScheduleError`.
- `@dataclass Schedule`: `times: list[str]` (sorted, duplicates collapsed), `apply: bool`, `apply_limit: int`.
- `get_schedule(conn) -> Schedule`; `set_schedule(conn, times: list[str], now: datetime | None = None) -> Schedule` (validates all before changing anything, replaces the old schedule, sets `schedule_last_slot` = `now`, so slots earlier than now are not fired); `clear_schedule(conn) -> None`; `set_apply(conn, on: bool | None = None, limit: int | None = None) -> Schedule` (`limit < 1` raises `ValueError`).
- `due_slot(conn, now: datetime) -> datetime | None`: the latest slot `s` with `schedule_last_slot < s <= now`, with slots being each configured `HH:MM` on each calendar day (in `now.tzinfo`) from the last-slot day to the `now` day; `None` if none or no schedule.
- `tick(conn=None, now: datetime | None = None, *, stages: Stages | None = None) -> RunSummary | None`: if `due_slot` is not `None`, stores it as `schedule_last_slot` (so the slot is consumed even when the run is rejected), then calls `runs.execute_run("scheduled", stages=stages, apply=schedule.apply, apply_limit=remaining, now=now)` and returns the summary. `remaining = max(0, schedule.apply_limit - tickets with submitted_at on the UTC day of now)`. Several missed slots start exactly one run. `RunInProgressError` is caught: logged, returns `None`, no row. `now` defaults to `datetime.now().astimezone()`.
- `serve(poll_seconds: float = 30, once: bool = False, stop: threading.Event | None = None, clock: Callable[[], datetime] | None = None, stages: Stages | None = None) -> None`: loops `tick` until `stop` is set; `once=True` ticks once and returns.

### `hireember.export`
- `export_csv(conn, out_dir: str | Path) -> list[tuple[Path, int]]`: writes `tickets.csv` (same header and rows as `web.queries.tickets_csv`) and `runs.csv` (header `id,kind,trigger,status,started_at,ended_at,found,scored,skipped,tickets_created,tickets_blocked`, one row per run, oldest first); the header is written even with zero rows; existing files are overwritten; returns `(path, row_count)` for each. If `out_dir` is missing, not a directory or not writable, raises `ExportError(message)` and writes nothing.

### CLI (`hireember ...`, Typer app `hireember.cli.app`)
- `schedule [--at HH:MM]... [--off] [--apply on|off] [--apply-limit N]`
  - `--at 08:00` (repeatable) prints `Schedule set: daily at 08:00.` (several: `daily at 08:00, 18:30.`) plus a line saying the schedule fires only while `hireember scheduler` is running and that a run missed while it was not running starts once at the next start. Exit 0.
  - Invalid time prints `Invalid time "25:00". Use 24-hour HH:MM, e.g. 08:00.` and exits 1; the schedule is unchanged.
  - `--off` prints `Schedule cleared.`.
  - No options prints `Scheduled daily at 08:00, 18:30.` or `No schedule set.`, then `Scheduled applying: off.` or `Scheduled applying: on (up to N per day).`.
  - `--apply on|off` / `--apply-limit N` update those settings (a bad value exits 1) and print the same applying line. Default is off, limit 25.
- `scheduler [--once] [--poll-seconds N]`: runs `scheduler.serve`; `--once` ticks once and exits 0.
- `company add "<name>" --url <careers-url> --ats <type>` prints `Added company "<name>".`; a duplicate prints `Company "<name>" already exists.` exit 1; an unknown type prints `Unknown ATS type "<x>". Valid types: workday, careers-page.` exit 1.
- `company remove "<name>"` prints `Removed company "<name>".`; an unknown name prints `Company "<name>" not found.` exit 1.
- `company list` columns `Id, Name, Careers URL, ATS, Manual-only`; empty prints `No companies yet.`.
- `run discover|score|tailor` (exactly one of these three stage names, no `--dry-run`, no `--stream`) runs only that stage via `runs.run_stage` and prints its result message line. A busy lock prints `A run is already in progress.` exit 1. Any other stage combination uses the existing pipeline path unchanged.
- `apply` (full apply mode) prints `apply: N submitted.` after the launcher returns, and takes the same lock (busy: `A run is already in progress.`, exit 1). The utility modes (`--mark-applied`, `--mark-failed`, `--reset-failed`, `--gen`) do not take the lock.
- `export [--out DIR]` prints one `Wrote <path> (N rows).` per file (`tickets.csv`, then `runs.csv`); on `ExportError` prints the reason and exits 1.
- `--help` exits 0 for `init, run, apply, status, dashboard, doctor, schedule, scheduler, export, answers, queue, company`, on a fresh install (no profile, no DB).

### HTTP (dashboard, `hireember.web.server.create_server(host, port, db_path=None, stages=None)`; `stages` is an optional `runs.Stages` injected for tests)
- `GET /` unchanged (byte-identical to `static/index.html`).
- `GET /runs` returns `200 text/html`, a full page containing a heading `Runs`; one table row per run, newest first, with start time, trigger, status and the five counts as plain integers in cells; with no runs it contains `No runs yet.`. `GET /runs?fragment=1` returns the same section without `<html>` wrapper. All values are HTML-escaped.
- `GET /api/runs` returns `{"runs": [{"id", "kind", "trigger", "status", "started_at", "ended_at", "found", "scored", "skipped", "tickets_created", "tickets_blocked"}]}`, newest first.
- `POST /api/stages/<discover|score|tailor|apply>` (JSON body optional `{"limit": int}`) returns `202 {"started": true, "stage": "<s>"}`. If the lock is held it returns `409 {"error": "A run is already in progress.", "code": "run_in_progress"}`. An unknown stage returns `404 {"code": "not_found"}`.
- `GET /api/stages/status` returns `{"running": bool, "last": {"stage", "message"} | null}`.
- UI: a tab button `Runs` (id `tab-runs`) and four buttons labelled `Run discover`, `Run score`, `Run tailor`, `Run apply`; a 409 shows the inline text `A run is already in progress.`.
