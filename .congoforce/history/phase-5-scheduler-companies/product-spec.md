# Product spec — Add scheduled runs, run summaries and a user-maintained company list

## User-facing behaviour

Existing surface (kept): `hireember init | run | apply | status | dashboard | doctor`, groups `answers` (`list`), `queue` (`list`, `answer`, `ready`), `company` (`manual`, `list`), `models`. `run` already accepts stage names (`discover`, `enrich`, `score`, `tailor`, `cover`, `pdf`) and `apply` is separate. `company list` currently shows Id, Name, Manual-only. `queue list` shows Id, Ticket, Kind, Company, Page, Question. No assets (mock-ups) exist for this task.

### 1. Schedule (`hireember schedule`)
- `hireember schedule --at 08:00` sets one daily run time (24-hour `HH:MM`, machine local time). `--at` may be repeated (`--at 08:00 --at 18:30`) for several daily times. Setting a schedule replaces the previous one.
- `hireember schedule` with no options shows the current schedule: "Scheduled daily at 08:00, 18:30." or "No schedule set."; also whether scheduled applying is on and the per-day limit.
- `hireember schedule --off` clears the schedule: "Schedule cleared."
- `hireember schedule --apply on|off` turns scheduled applying on or off (default off). `--apply-limit N` sets the per-day apply limit used by scheduled runs.
- Confirmation after setting: "Schedule set: daily at 08:00." A scheduled run needs no dashboard and no open terminal; the user is told in the confirmation what must stay running or installed for it to fire (exact mechanism is a tech-spec choice; the output must not claim more than it does).
- Invalid time (e.g. `25:00`, `8am`): print "Invalid time "<value>". Use 24-hour HH:MM, e.g. 08:00." and exit 1; schedule unchanged.

### 2. Runs and summaries
- A run = discover, score, tailor (plus enrich/cover/pdf as the pipeline already requires), and, only if scheduled applying is on, apply.
- When a run ends it writes exactly one `runs` row: start and end time, trigger (scheduled / manual), status, and counts: roles found, scored, skipped, tickets created, tickets blocked.
- Dashboard shows a "Runs" section, newest first, one row per run with those five counts, start time, trigger and status. Empty state: "No runs yet."
- Run log records per-source failures (see Discovery).

### 3. Single run at a time
If a run is in progress, any further trigger (scheduler, CLI, dashboard) does not start another and creates no `runs` row. A CLI/dashboard trigger rejected for this reason says: "A run is already in progress." (CLI exit 1). A scheduler trigger that is skipped stays silent apart from a log line.

### 4. Single stages on demand
`hireember run discover`, `run score`, `run tailor`, and `hireember apply` each run only that stage and print its result (e.g. "discover: 42 roles found, 5 new." / "score: 30 scored, 12 skipped." / "tailor: 8 tickets created, 2 blocked." / "apply: 3 submitted."). The same single-stage start is available as buttons on the dashboard. A single-stage start does not run the other stages.

### 5. Blocked tickets in the queue
Each ticket a run blocks because it needs a human appears in the action queue (`queue list` and dashboard) with company name, reason and page link, once per blocked ticket (no duplicates on re-runs).

### 6. Company list
- `hireember company add "<name>" --url <careers-url> --ats <type>` adds a company; "Added company "<name>"." `--ats` accepts the ATS types already supported in `discovery/`; an unknown type lists the valid ones and exits 1.
- `hireember company remove "<name>"` removes it: "Removed company "<name>"." Unknown name: `Company "<name>" not found.` exit 1.
- `hireember company list` gains Careers URL and ATS columns (existing Id, Name, Manual-only kept). Empty: "No companies yet."
- Discovery searches exactly the companies in this list. A small example `employers.yaml` ships as a starting point; no large employer list ships.
- Adding a company that already exists (same name, case-insensitive): "Company "<name>" already exists." exit 1.

### 7. Discovery results
Each stored role has company, title, location, source, URL and date found. Seeing a role again updates its last-seen time and creates no second record. If one source fails, the failure is logged against that source (source name and error message) in the run log and the other sources still run; the run still completes and writes its row.

### 8. Export
`hireember export [--out DIR]` writes two CSV files, `tickets.csv` and `runs.csv`, to the given directory (default current directory) and prints "Wrote <path> (N rows)." for each. Header row is always present, including when there are zero rows. Existing files are overwritten.

### 9. Missed runs
If the machine was asleep or off at a scheduled time, one run starts at the next start (not one per missed slot). The README states this in a "Scheduled runs" section.

### 10. Help
Every command and group prints help and exits 0, on a fresh install (no profile, no database).

## Acceptance criteria
- AC-1: With a test clock and schedule `--at 08:00`, advancing to 08:00 starts one scheduled run (trigger "scheduled") with no dashboard running; when it ends exactly one `runs` row exists with integer counts for found, scored, skipped, tickets created and tickets blocked (0 allowed). Advancing time past 08:00 again within the same day starts no second run.
- AC-2: Two overlapping triggers (any mix of scheduler/CLI/dashboard) produce exactly one `runs` row; the second trigger starts nothing and, if manual, prints "A run is already in progress."
- AC-3: With scheduled applying off (the default), a scheduled run never calls the browser launcher; apply is not run at all.
- AC-4: Discovery over a three-company fixture list stores each role with non-empty company, title, source, URL, date found, and location (empty location allowed only if the source gave none). A second run leaves one record per role and a later last-seen time than after the first run.
- AC-5: A failing source produces a run-log entry naming that source and the error; the other sources are still searched and their roles stored; the run still writes its `runs` row.
- AC-6: After `company add`, the next run searches the new company; after `company remove`, the next run does not search it. Output messages as in section 6.
- AC-7: `hireember schedule --help`, `export --help` and `answers --help` exit 0, and `--help` exits 0 for init, run, apply, status, dashboard and doctor, on a fresh install.
- AC-8: After a run that blocks N tickets, `queue list` shows N new items, each with company name, reason and page link (none empty). Re-running does not duplicate them.
- AC-9: The dashboard HTML contains, for each run, its found, scored, skipped, tickets created and tickets blocked counts. With no runs it contains "No runs yet."
- AC-10: With a test clock where 08:00 passed while the app was not running, the next start launches exactly one run (even if several slots were missed); the README documents this behaviour.
- AC-11: With scheduled applying on, a scheduled run applies only to eligible tickets and submits no more than the per-day limit, counting applications already made that day.
- AC-12: `run discover`, `run score`, `run tailor` and `apply` each run only their own stage and print a result line (section 4); the other stages do not run. The dashboard offers the same.
- AC-13 (implied by Gate 1 answers): `hireember schedule --at HH:MM` (repeatable) is the way to set the schedule; invalid values are rejected per section 1.
- AC-14 (implied by Gate 1 answers): `hireember export` writes `tickets.csv` and `runs.csv` with a header row each and one row per ticket / run.

## Edge cases and errors
- No schedule set: nothing fires; `schedule` shows "No schedule set."
- Duplicate times in `--at` are collapsed to one.
- A run interrupted by process death does not block future runs forever; its row, if any, is marked as failed/interrupted.
- All sources fail: run still ends, one row with zero found, failures logged.
- Empty company list: discovery finds nothing and says "No companies to search. Add one with `hireember company add`."
- Scheduled applying on but per-day limit already reached: apply is skipped, run still completes.
- Export to a non-writable or missing directory: print the reason, exit 1, write nothing.
- Role seen again keeps its original date found.

## Out of scope
- Shipping a large employer list (only a small example `employers.yaml`).
- Phase 4 work.
- New ATS adapters beyond those in `discovery/`.
- Exporting answers; JSON or other formats.
- Cron expressions and interval schedules.

## Open questions
- Should the dashboard be able to edit the schedule, or is `hireember schedule` the only place?
- Is the default per-day apply limit an existing setting to reuse, or does scheduled applying get its own default?
- Should the run-in-progress rejection from the dashboard be an inline message or a toast? (copy above assumes inline)
