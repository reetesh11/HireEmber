# Interface contract — phase-1-data-layer

All functions take a `sqlite3.Connection` as returned by `hireember.database.init_db(path)` (row factory `sqlite3.Row`). Rows are returned as plain `dict`.

### `hireember.database`
- `init_db(db_path: Path | str | None = None) -> sqlite3.Connection` — unchanged signature. Now also: backs up an existing database that would change, creates the new tables/columns, migrates tickets. Idempotent. Raises `hireember.migration.MigrationError` if the backup cannot be written (message starts `Backup failed; the database was not changed:`) and then touches nothing.
- `ensure_columns(conn) -> list[str]` — now also adds to `jobs`: `company_id INTEGER`, `title_normalized TEXT`, `location_normalized TEXT`, `last_seen_at TEXT`.
- `store_jobs(conn, jobs, site, strategy) -> tuple[int, int]` — same return/insert/skip behaviour. New: sets `title_normalized`, `location_normalized`, `last_seen_at` on insert; on an already-stored URL updates only `last_seen_at`; optional `job["company"]` sets `company_id`.
- Existing `get_stats` is unchanged.

### `hireember.migration`
- `class MigrationError(RuntimeError)`.
- `migrate_database(db_path: Path | str) -> Path | None` — calls `init_db(db_path)` semantics (closing nothing) and returns the path of the backup created by this call, or `None` when no backup was needed (fresh install or already migrated). Safe to call repeatedly.
- Backup file: same directory, name `<db file name>.bak-<YYYYMMDDTHHMMSSZ>`, openable as SQLite with the original `jobs` rows. Glob for tests: `<db name>.bak-*`.
- Tables created: `companies`, `tickets`, `ticket_events`, `queue_items`, `answers`, `resumes`, `runs`, `settings`.

### `hireember.tickets`
- `ALLOWED_STATUSES: tuple[str, ...]` = `("pending", "started", "applying", "blocked for human", "applied", "skipped", "closed")`.
- Exceptions: `TicketError(Exception)`; `InvalidStatusError(TicketError, ValueError)` (message names the value and lists allowed ones); `TicketNotFoundError(TicketError)` (message `Ticket <id> not found.`); `DuplicateTicketError(TicketError)` with attributes `ticket_id: int`, `duplicate_of: int`, message `Ticket <id> is a duplicate of ticket <other id>; not started.`; `OverrideReasonError(TicketError)` (message `An override needs a reason.`).
- `normalize_text(value: str | None) -> str` — lowercase, replace punctuation with a space, collapse whitespace, trim; `None` gives `""`. `normalize_text("  Senior  Engineer (Remote) ") == "senior engineer remote"`.
- `get_or_create_company(conn, name: str) -> int` — case-insensitive lookup on trimmed name; creates `companies` row if missing.
- `set_job_company(conn, url: str, name: str) -> int` — sets `jobs.company_id`, returns company id.
- `get_threshold(conn) -> int` — `settings` key `score_threshold`; missing/non-numeric/empty gives 7.
- `set_setting(conn, key: str, value: str) -> None` — upsert into `settings`.
- `set_job_score(conn, url: str, score: int, reasoning: str = "") -> int` — updates `jobs.fit_score`, `score_reasoning`, `scored_at`, then ensures one ticket and returns its id. New ticket: `pending` if `score >= threshold` else `skipped`; first event actor `system`, reason `score <n> meets threshold <t>` or `score <n> below threshold <t>`; ticket `score`/`score_reason` filled. If a ticket for the URL exists, it is returned unchanged (status untouched; score fields may be refreshed).
- `ensure_ticket(conn, url: str) -> int` — same ticket creation for a job that already has `fit_score` set (used when tests set the score directly). Raises `TicketError` if the job does not exist or has no score.
- `get_ticket(conn, ticket_id: int) -> dict` — keys include `id, job_url, status, status_reason, duplicate_of, unverified, score, score_reason, created_at, updated_at`. Raises `TicketNotFoundError`.
- `get_ticket_by_url(conn, url: str) -> dict | None`.
- `set_status(conn, ticket_id: int, status: str, *, actor: str = "system", reason: str = "", link: str | None = None, link_kind: str | None = None, override_reason: str | None = None) -> None`
  - Invalid status: `InvalidStatusError`, nothing written. Invalid actor (not `system`/`user`): `ValueError`. Unknown id: `TicketNotFoundError`.
  - Same status as current: no-op, no event.
  - Otherwise updates `tickets.status`, `status_reason`, `updated_at` and writes one `ticket_events` row.
  - When `status == "started"`: duplicate check first (match rule and blocking statuses per product spec; oldest matching ticket id is linked). On blocking match without override: sets ticket to `blocked for human`, reason `duplicate`, `tickets.duplicate_of = <other id>`, event actor `system` with `link = str(other id)`, `link_kind = "duplicate-of"`, commits, then raises `DuplicateTicketError`. A ticket already `blocked for human` with reason `duplicate` asked again is refused with the same error and no new event. Non-blocking or no match: proceeds.
  - `override_reason` given with a blocking match (or on a ticket blocked as duplicate): empty/whitespace raises `OverrideReasonError` with nothing written; otherwise writes an override event (`actor "user"`, `reason = override_reason`, `link = str(other id)`, `link_kind = "override"`, `status` = the ticket's current status), then moves to `started` with a second event; `duplicate_of` stays set. The other ticket is not altered.
- `get_history(conn, ticket_id: int) -> list[dict]` — oldest first (by event id). Each dict has keys `id, ticket_id, status, actor, reason, link, link_kind, time` (`time` is UTC ISO 8601).

### Match rule details (observable through `set_status`)
Application URL = `jobs.application_url`, falling back to `jobs.url` when empty. Company key = `lower(trim(companies.name))` via `jobs.company_id`, else `lower(trim(jobs.site))`; with `title_normalized` and `location_normalized`. If any of company, title or location is empty the text key does not match; the URL key still does.

### Migrated tickets (via `init_db` / `migrate_database`)
One ticket per `jobs` row with non-empty `apply_status` or non-empty `tailored_resume_path`, status and first-event reason per the req.md R3 table, actor `system`; `applied` rows have `tickets.unverified = 1`; `failed` uses the exact `apply_error` (empty string if none); unknown status gives `blocked for human` with `unknown status: <value>`. `tickets.score` copies `fit_score`. No duplicate check.
