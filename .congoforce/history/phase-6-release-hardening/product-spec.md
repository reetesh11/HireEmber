# Product spec - Release hardening: logs, token totals, key scan, traceability and docs

## User-facing behaviour

Existing surface: the dashboard (`src/hireember/web/server.py`) serves a ticket list, a ticket detail page (`GET /api/tickets/<id>` payload plus page), and a runs view (`/runs`, `/api/runs`). The CLI is `hireember`. Docs today: `README.md`, `CONTRIBUTING.md`, `docs/traceability.md` (6 rows). `docs/safety.md` does not exist.

### Logs
- Every pipeline run writes one log file, created when the run starts, in the HireEmber data folder (`HIREEMBER_DIR`) under a `logs/` subfolder (for example `logs/runs/run-<id>.log`). Exact file naming is a tech-spec decision; the user-visible rule is one file per run and one per ticket attempt.
- Every application attempt for a ticket writes a log file for that attempt (for example `logs/tickets/ticket-<id>-attempt-<n>.log`). A ticket with several attempts has one file per attempt, and the ticket page links to each (newest first).
- Logs are plain text, one event per line with a timestamp. The ticket attempt log keeps what FR/SAF-5 and SAF-11 already require (field and source of value; injected-instruction note) so those entries stay readable here.
- Logs are never written inside the repository.
- Logs older than 90 days are pruned automatically (see AC-7).

### Dashboard links
- Runs view: each run row has a link labelled "Log" opening the run log as plain text (`text/plain; charset=utf-8`) at a local dashboard URL (for example `/logs/runs/<id>`).
- Ticket page: a "Logs" section lists one link per attempt, labelled "Attempt <n> log". A ticket with no attempt shows the text "No attempt log yet."
- A run or attempt whose file has been pruned or deleted still shows its row, with the link replaced by the text "Log removed".
- Log URLs serve only files inside the logs folder; they accept an id, never a path.

### Model and token totals
- When a scoring, tailoring or applying stage finishes for a ticket, the stage's model name and token counts (input, output, total) are recorded against that ticket and stage. A stage run again adds to that stage's totals; the page shows the latest model and the summed tokens.
- Ticket page gets a "Model and tokens" table with three rows: Scoring, Tailoring, Applying. Columns: Stage, Model, Input tokens, Output tokens, Total tokens.
  - Recorded stage: for example `Scoring | claude-sonnet-5-5 | 1,200 | 150 | 1,350`.
  - Stage with no record: Model shows `-` and the three token cells show `-`. It is an explicit empty value, not an error and not zero.
  - Stage where the provider gave no token data: the model name is shown and tokens show `0`.
- The ticket API payload (`GET /api/tickets/<id>`) carries the same data as `usage`: an object with keys `scoring`, `tailoring`, `applying`, each either `null` (no record) or `{"model": str, "input_tokens": int, "output_tokens": int, "total_tokens": int}`.
- No currency cost is shown.

### Keys and telemetry
- No change visible in the UI. The repository and database never hold an API key; keys live only in a git-ignored `.env`. `.env.example` is committed and not ignored. The product sends no telemetry.

### Traceability table
- `docs/traceability.md` gains one row per FR, SAF and NFR ID in `OpenApply — Requirements Document.md` (about 75). Columns stay: Requirement, Description, Tests. Each test cell names existing files under `tests/` or `.github/workflows/`, with `::test_name` where given.
- IDs the requirements document marks as later or out of scope are listed in an "Exempt" section of the same file, each with the reason.
- IDs that have no test today are listed in a "Known exceptions" section of the same file and in `docs/parked-fixes.md`; the completeness test allows exactly those IDs. This task does not write tests for them.

### Docs
- `README.md`: a "Setup" section (heading text "Setup to your first scored role") with numbered steps: install, `hireember init` (resume, profile and the other init questions), run discovery, run scoring, open the dashboard and see a scored role. No step asks the user to edit code. It states in one sentence: "Schedules do not fire while the machine is asleep; a missed run starts at the next scheduled time after wake." (wording final in implementation, but it must contain "do not fire while the machine" and "asleep" or "sleeps").
- `CONTRIBUTING.md`: a "Safety rules" section restating section 7 (SAF-1 to SAF-12), including no LinkedIn, no auto-submit without the human gate, and no telemetry, and the rule that docs change in the same PR as behaviour (NFR-12).
- `docs/safety.md`: new page with the same rules in user language, one heading per rule group, plus where data goes (only the user's configured LLM provider and the company sites applied to) and where keys live.

## Acceptance criteria

- AC-1: After a pipeline run starts, a log file for that run exists under `HIREEMBER_DIR/logs`. After an application attempt, a log file for that attempt exists. The runs view contains a "Log" link per run, and the ticket page contains an "Attempt <n> log" link per attempt. Each link returns HTTP 200, content type `text/plain`, and a body equal to the file text. A missing file returns HTTP 404 with a short message "Log not found." and the page shows "Log removed" instead of a link.
- AC-2: For a ticket with recorded scoring, tailoring and applying stages, the ticket page and the `usage` object in its API payload show, for each stage, the model name and input, output and total tokens. A stage with no record shows `-` on the page and `null` in the API, with HTTP 200 and no error.
- AC-3: A test scans all git-tracked files and a seeded database (every text column of every table) for API-key patterns: the Anthropic key prefix (`sk` then `-ant-`), `sk-` followed by 20 or more alphanumeric, `-` or `_` characters, and `AIza` followed by 35 characters; it finds none. `git check-ignore .env` exits 0 and `git check-ignore .env.example` exits non-zero. The scan's own patterns are built so the test file does not trigger itself.
- AC-4: `docs/traceability.md` has a row for every FR-, SAF- and NFR- ID found in `OpenApply — Requirements Document.md`, or lists it under Exempt (with reason) or Known exceptions (also in `docs/parked-fixes.md`). Each non-exempt row names at least one existing test file, and a named `::test_name` must exist in that file. A test fails with a message naming the ID when an ID is missing from the table, maps to a nonexistent file or test, or is listed as an exception without an entry in `docs/parked-fixes.md`. A test also fails if an exempt ID is not marked later or out of scope in the requirements document.
- AC-5: `README.md` has the setup section described above, going from install through `init` to a first scored role with no code edit, and contains the sleep statement. `CONTRIBUTING.md` and `docs/safety.md` exist and each contains the phrases "LinkedIn", "human gate" (or "gate"), "telemetry" and every ID SAF-1 to SAF-12. A test checks the required headings and phrases in all three files.
- AC-6: A test finds no import of an analytics or telemetry client (for example `sentry_sdk`, `posthog`, `segment`, `mixpanel`, `amplitude`, `opentelemetry`, `datadog`) and no outbound call to a telemetry host in `src/hireember`, and `pyproject.toml` lists none of them as a dependency.
- AC-7 (implied by gate 1 answer 2): Log files older than 90 days are deleted when a run starts. Newer files are untouched. Ticket and run records remain; the dashboard shows "Log removed" for pruned files. A test covers a file 91 days old (deleted) and 89 days old (kept).

## Edge cases and errors
- Log folder cannot be written (permissions, disk full): the run or attempt continues, a warning is printed once to the console, and the dashboard shows "Log removed" for that entry.
- Provider returns no token data: record model name and zero tokens (shown as `0`). Model unknown: show `unknown`.
- Ticket with no stages run yet: all three rows show `-`; page loads normally.
- Tickets created before this change have no usage or log records: same empty display; no migration errors.
- A stage that fails midway still records whatever tokens were spent before the failure.
- Log URL for a non-numeric id or an id with path characters returns 404, never a file outside the logs folder.
- Log text containing HTML is served as plain text, not rendered.
- A secret value must not be written into logs; the key scan covers the database and tracked files, and the log writer must not echo environment variable values.
- Traceability: duplicate IDs in the table, IDs written in the table that are not in the requirements document, and an empty Tests cell all fail the test.

## Out of scope
- New product features beyond logs, token display and docs.
- Cost in currency.
- Rewriting existing tests, except to fill traceability gaps.
- Writing tests for requirements with no test today (they go to `docs/parked-fixes.md` as known exceptions).
- Changing the scheduler to fire during sleep.
- A log viewer with search or filtering, or log download.

## Open questions
- none (gate 1 answers settle exemptions, 90-day retention and parked exceptions). Minor wording of README and docs is left to implementation within the phrases fixed above.
