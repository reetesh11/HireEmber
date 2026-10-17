# Product spec — Add ticket data layer, ApplyPilot migration and duplicate detection

## User-facing behaviour

This phase has no screens, CLI commands or dashboard views. The "user" is the person running HireEmber and the later phases that call the data layer. What they see is: (a) what happens to their existing database on first start, (b) the rows that appear in the database, and (c) the Python-level behaviour of scoring, status changes and duplicate checks. Existing behaviour of `init_db`, `store_jobs` and `get_stats` (in `src/hireember/database.py`) does not change.

### Database start-up and migration
- On start-up (`init_db`), HireEmber opens `hireember.db` in `~/.hireember` (or `HIREEMBER_DIR`). A user who only has the legacy folder runs on `applypilot.db`, read in place. The migration behaves the same on either file name, and the file keeps its own name.
- Fresh install (file does not exist): no backup is made, tables are created, no tickets exist.
- Existing file that the migration will change: before any change, the file is copied next to itself. Backup name pattern: `<original file name>.bak-<UTC timestamp YYYYMMDDTHHMMSSZ>`, for example `applypilot.db.bak-20261017T093000Z`. The backup sits in the same directory as the database. The backup is a complete, openable SQLite copy. If a backup cannot be written, the migration stops before changing anything and reports an error (see Edge cases).
- Existing file that is already fully migrated: nothing changes, no new backup is required.
- All nine tables exist afterwards: `companies`, `tickets`, `ticket_events`, `queue_items`, `answers`, `resumes`, `runs`, `settings` (plus the existing `jobs`).
- `jobs` keeps every row and every existing column value. It gains four columns: company id, normalized title, normalized location, last seen. Normalized title and location are filled for all rows, existing and newly stored.
- Columns the other tables carry follow the data model in `input.md` (tickets: job URL, status, status reason, resume id, tailored resume path, cover letter path, score, score reason, duplicate-of, unverified flag, referral note, notes, created, updated; ticket_events: ticket id, status, actor, reason, link, link kind, time; and so on). The companies, resumes, answers, queue_items and runs tables are created empty and not populated.

### Normalization (visible through duplicate detection)
- Title: lowercase, trim, replace punctuation with a space, collapse runs of whitespace to one space. "  Senior  Engineer (Remote) " and "senior engineer remote" normalize to the same value.
- Location: same rules as title.
- Company in the duplicate key: lowercased and trimmed. "Acme" and "ACME" match.
- Empty values: a role with no company, title or location text never matches another role on the company/title/location key (an empty part is not a match). The application-URL key still applies.

### Migrated tickets
One ticket per `jobs` row that has been tailored or attempted (that is, `apply_status` is set, or the row has a tailored resume). Status and the first history event, per old `apply_status`:

| Old `apply_status` | Ticket status | Reason on first `ticket_events` row |
| --- | --- | --- |
| empty (tailored resume exists), `tailored` | pending | none (empty) |
| `in_progress` | pending | `stale lock from an interrupted run` |
| `applied` | applied | `unverified` (ticket's unverified flag is set) |
| `failed` | blocked for human | the stored `apply_error` text |
| `manual` | blocked for human | `manual ATS` |
| `captcha` | blocked for human | `CAPTCHA` |
| `login_issue` | blocked for human | `account needed` |
| `expired` | closed | `role expired` |

- The first event has actor `system`.
- Migrated tickets are not duplicate-checked; they record history, they do not start work.
- Jobs rows that were neither tailored nor attempted get no ticket from the migration (they get one when scored, see below).

### Scoring creates tickets
- When a role gets a fit score, exactly one ticket exists for it afterwards. Score at or above the threshold: pending. Below: skipped.
- Threshold comes from the `settings` row with key `score_threshold`; if absent, 7. (Key name proposed; see Open questions.)
- Re-scoring a role that already has a ticket creates no second ticket. A role that already has a ticket is not moved by re-scoring (status only changes through the status-change path below).
- Each new ticket gets a first history event with actor `system` and reason `score <n> meets threshold <t>` (pending) or `score <n> below threshold <t>` (skipped).

### Ticket statuses and history
- Allowed statuses, exact spellings: `pending`, `started`, `applying`, `blocked for human`, `applied`, `skipped`, `closed`.
- Any other value is rejected with an error naming the value and listing the allowed ones, and nothing is written (no status change, no event).
- Every status change writes one `ticket_events` row: status, actor (`system` or `user`), reason (may be empty), optional link and link kind, time (UTC, ISO 8601). Creating a ticket also writes its first event.
- Asking for the status the ticket already has is not a change and writes no event.
- The history of a ticket is returned oldest first, one entry per event, in the order they were written.

### Duplicate detection
- Trigger: any request to move a ticket to `started`. The check runs before the move and before any browser work.
- Match rule: another ticket (not itself) whose job has the same application URL, or the same lowercased company, normalized title and normalized location. Application URL is `jobs.application_url`, falling back to `jobs.url` when empty.
- Blocking matches: the other ticket is `started`, `applying`, `blocked for human` or `applied`. Non-blocking: `pending`, `skipped`, `closed`.
- On a blocking match: the new ticket is set to `blocked for human` with reason `duplicate`, `duplicate-of` stores the existing ticket's id, the event carries a link to the existing ticket (link kind `duplicate-of`), actor `system`. The ticket does not move to started, and the request fails with a message: `Ticket <id> is a duplicate of ticket <other id>; not started.`
- If several blocking matches exist, the oldest ticket (lowest id) is the one linked.
- A ticket already `blocked for human` for reason `duplicate` that is asked again to move to started is refused the same way, without writing another event.
- Non-blocking match or no match: the move to started proceeds and is recorded.
- The reason is shown in this phase only as the stored status reason and link (no UI).

### Override
- A user can override the duplicate block for one ticket by supplying a non-empty reason. The ticket then moves to `started`, and `ticket_events` holds an override event with actor `user`, the supplied reason (for example `reapplying`), and a link to the matched ticket. The move to started itself is also recorded as an event.
- Override with an empty or whitespace-only reason is refused: `An override needs a reason.` No change is written.
- The override applies to that ticket only and does not alter the other ticket. `duplicate-of` stays set for the record.

## Acceptance criteria

- AC-1: Migrating a fixture DB with at least one `jobs` row for each of empty, `tailored`, `in_progress`, `applied`, `failed`, `manual`, `captcha`, `login_issue`, `expired` creates all eight new tables plus keeps `jobs`. Each fixture row that was tailored or attempted gets exactly one ticket whose status and first-event reason match the table above (failed uses the row's exact `apply_error`; applied has unverified flag set). Event actor is `system`. A file named `<db file name>.bak-<timestamp>` exists in the DB's directory and opens as a SQLite database with the original `jobs` rows. All fixture `jobs` rows are still present. Normalized title, normalized location and last seen columns exist on `jobs`; normalized values are filled.
- AC-2: Running the migration a second time leaves the table list, ticket count, `ticket_events` count and `jobs` row count identical to after the first run, and creates no further backup file (a no-op rerun skips it). Passes for a fixture saved as `applypilot.db` and as `hireember.db`.
- AC-3: With default threshold 7, scoring a role with score 7 gives exactly one ticket (`pending`) and scoring a role with score 6 gives exactly one ticket (`skipped`). Re-scoring either role (same or different score) leaves exactly one ticket per role. With `settings` threshold set to 8, a score of 7 gives `skipped`.
- AC-4: After a sequence of status changes on one ticket (for example pending, started, applying, applied), its history returns one event per change, oldest first, each with time, actor and reason fields present. A status outside the seven allowed values is rejected with an error, and the history is unchanged.
- AC-5: Two scored roles with the same company (compared case-insensitively), normalized title and normalized location, or the same application URL: asking the second ticket to move to started leaves it `blocked for human` with reason `duplicate` and `duplicate-of` set to the first ticket's id, and the call fails with `Ticket <id> is a duplicate of ticket <other id>; not started.` A match whose ticket is only `pending`, `skipped` or `closed` does not block: the move to started succeeds. Matches in `started`, `applying`, `blocked for human` and `applied` each block.
- AC-6: Overriding the block with reason `reapplying` lets the ticket move to `started`. `ticket_events` holds an event marking the override with reason `reapplying` and actor `user`. An override with an empty reason is refused.
- AC-7: The existing test suite for `init_db`, `store_jobs` and `get_stats` passes unchanged. `get_stats` counts and `store_jobs` insert/skip behaviour are the same as before for databases with and without the new tables.

## Edge cases and errors
- Fresh install: no backup, empty new tables, no error.
- Backup cannot be written (read-only folder, disk full): migration stops before touching the database; the error says the backup failed and that the database was not changed.
- Backup name already exists (two runs in the same second): a distinct name is used; an existing backup is never overwritten.
- Migration interrupted part way: running it again completes it without duplicate tickets or events (same result as AC-2).
- `jobs` row with `apply_status` of `failed` and empty `apply_error`: ticket is blocked for human with an empty reason.
- `jobs` row with an unknown `apply_status` value (not in the table): treated as attempted; ticket is `blocked for human` with reason `unknown status: <value>`. (See Open questions.)
- A job already scored and already migrated: no second ticket from scoring.
- Unscored roles have no ticket until scored.
- Missing, non-numeric or empty `score_threshold` setting: default 7 is used.
- Moving a ticket that does not exist: error `Ticket <id> not found.`
- Two roles with the same company but different location, or same title but different company: not duplicates.
- Roles with empty company/title/location are not matched on that key (URL key still applies).
- Same ticket cannot be a duplicate of itself.

## Out of scope
- Per-company and per-day limits (FR-DUP-4, phase 3).
- Dashboard views of tickets (phase 4), CLI commands, and any visible screen.
- Populating `resumes`, `answers`, `companies` beyond creating the tables.
- Browser work, applying, and queue item creation.

## Open questions
- Unknown old `apply_status` values (none expected): req.md lists only nine values. Should an unexpected value be migrated as blocked for human with reason `unknown status: <value>` (proposed above), or left without a ticket?
- Backup file naming (`<db name>.bak-<UTC timestamp>`) and the settings key name (`score_threshold`) are proposed here; req.md only requires "a backup file next to it" and a settings key with default 7. Confirm or leave to tech-spec.
