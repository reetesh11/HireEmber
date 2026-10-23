# Product spec — Local web dashboard with ticket board, blocked queue, answer editing and CSV export

Decisions from `answers.md` (binding): one PR for all four parts; notes and referral notes live in a new notes column on the ticket (with a migration), and each manual change still writes a `ticket_events` row; resume editing covers metadata and replacing the file. Product name in all copy is "HireEmber"; the CLI command is `hireember`.

## User-facing behaviour

### Starting the dashboard
- New command `hireember dashboard` (name chosen to match the existing command style: `init`, `run`, `doctor`, `ticket`, `resume`, `answers`, `queue`).
- Options: `--port` (default 8765) and `--host` (default and only accepted value `127.0.0.1`).
- On start it prints `HireEmber dashboard running at http://127.0.0.1:8765 (local only). Press Ctrl+C to stop.` and does not open a browser unless `--open` is passed.
- `--host 0.0.0.0` (or any value other than `127.0.0.1`) exits with code 2 and prints `Refusing to bind to <host>. The dashboard is local only and binds to 127.0.0.1.` Nothing is listened on.
- If the port is in use: `Port <n> is already in use. Choose another with --port.` and exit code 1.
- If no database exists yet: the dashboard still starts and shows empty states (below); it does not create tickets.
- `hireember --help`, `hireember doctor` messages and any hard-coded command listings include the `dashboard` command with the help text "Open the local web dashboard."

### Layout
One page with a top navigation of four tabs: **Tickets**, **Blocked** (with a count badge, for example `Blocked (3)`), **Answers**, **Resumes**. The Tickets tab has a **Board / List** toggle, a filter bar and an **Export CSV** button.

### Tickets: board
- One column per entry in `ALLOWED_STATUSES`, in that order: pending, started, applying, blocked for human, applied, skipped, closed. Each column header shows the status name and the count of tickets in the current filtered view.
- Each card shows company, title, score (or `-` if unscored), resume name (or `-`), and the status link (see Links). Clicking a card opens the ticket detail panel.
- No drag-and-drop. Status is changed in the detail panel.
- An empty column shows `No tickets`.

### Tickets: list
- A table with columns Company, Title, Location, Status, Score, Resume, Applied, Link. Clicking a column header sorts ascending, again descending; the active sort shows an arrow. Default sort: most recently updated first.
- Same filtered set as the board.

### Filters
- Company (text, case-insensitive substring match against company name), Score (minimum and maximum, integers 0-100), Date (from and to, by the ticket's applied date when set, otherwise its created date; the same field is used in CSV "applied date" only when applied), Resume (dropdown of resumes plus "Any").
- Filters combine with AND. A **Clear filters** button resets all. Filter state is kept in the page URL query string so a reload keeps the view and the CSV export uses the same filters.
- When the filters match nothing: `No tickets match these filters.` with a Clear filters link.

### Links (R1)
Each ticket shows one link by status, labelled:
- pending: `Job posting` (the job URL)
- started: `Tailored files` (link to the tailored resume/cover files the ticket stores)
- applying: `Live browser session` (the session link recorded on the ticket)
- blocked for human: `Page needing action`
- applied: `Confirmation`
- skipped and closed: the job posting link if one exists (label `Job posting`).
Where no link is stored the card, row and detail panel show the text `No link available` in place of the link. Links to web pages open in a new tab; links to local files are shown as the file path text with a `Copy path` action, since browsers do not open local files from a page (see Open questions).

### Ticket detail panel
Shows all ticket fields, the status link, the blocked reason and next step when blocked, the notes and referral note, and the history (`ticket_events`, newest first: time, status, actor, reason). Controls:
- **Status**: dropdown of all seven statuses plus an optional reason box and **Change status** button. Goes through `tickets.set_status` with actor "user". Success toast: `Status changed to <status>.` Selecting the current status does nothing.
- **Notes**: multi-line text area with **Save note**. Free text, any length up to 10,000 characters.
- **Referral note**: separate multi-line text area with **Save referral note**. Free text.
- Moving a ticket to "started" when it is a duplicate follows existing duplicate rules: the panel shows the existing message (`Ticket <id> is a duplicate of ticket <n>.` style from `DuplicateTicketError`) and offers an **Override** field requiring a non-empty reason, matching `override_reason` behaviour. An empty override reason shows the existing `OverrideReasonError` message.

### Blocked queue
- The Blocked tab lists every ticket with status "blocked for human", independent of the Tickets filters, with the heading `Blocked for you (N)`; N equals the number of such tickets.
- Each entry: company, title, reason, next step, and the page link (or `No link available`).
- Next step is derived from the reason / queue kind with no invented reasons:
  - account needed -> `Create an account`
  - captcha -> `Solve the CAPTCHA`
  - identity check, video or biometric, manual site -> `Review` the page and finish by hand (copy: `Review and complete this step yourself`)
  - unknown question, conflicting answers, sensitive question -> `Answer the question` (shows the question text and an inline answer box, using the same rule as `answers.answer_queue_item`)
  - review before submit, outcome unknown -> `Review`
  - sign-in related reasons surfaced by the existing data -> `Sign in`
  - duplicate or any reason not in the list -> `Review`
- Empty: `Nothing is blocked. You're all caught up.`

### Live updates (R6)
- An open dashboard picks up a status change written to the database (by a running job or by the user in another tab) within 5 seconds, without reload: the card moves column, list row updates, counts and Blocked badge update. No data the user is typing (open note boxes) is lost on update.
- A small indicator shows `Live` when connected and `Reconnecting...` if the connection drops, retrying automatically.

### CSV export (R8)
- **Export CSV** downloads `hireember-tickets-YYYY-MM-DD.csv` for the current filtered view (including its sort order).
- Header row exactly: `company,title,location,status,score,resume used,applied date,links,notes`.
- One row per ticket. Applied date is ISO 8601 date (`YYYY-MM-DD`) or empty. Links is the ticket's status link(s), joined with a space; empty if none. Notes contains the ticket note followed, if present, by `Referral: <referral note>` on a new line. Fields containing commas, quotes or newlines are quoted per RFC 4180. Encoded UTF-8 with BOM so spreadsheets open it correctly. An empty filtered view downloads header row only.
- Cells that start with `=`, `+`, `-` or `@` are prefixed with a single quote `'` to prevent spreadsheet formula execution.

### Answers tab (R7)
- Table of stored answers: question, answer, source, last updated. Sensitive questions follow existing `SensitiveQuestionError` rules.
- **Edit**: inline edit of the answer text (and question text); saving shows `Answer saved.` An empty answer is rejected: `Answer cannot be empty.`
- **Merge**: select two answers, choose which question text and answer to keep, confirm. Result is one entry; the other is removed. Confirmation copy: `Merge these two answers into one? The other entry will be deleted.` Merging an answer with itself is not possible; fewer than two selected disables the button.
- **Delete**: confirmation `Delete this answer? This cannot be undone.`; on confirm the entry disappears.
- Empty: `No stored answers yet. Answers you give are saved here.`
- Changes persist and are visible after reload.

### Resumes tab (R7)
- Table of base resumes: name, tags, pinned, file name. Actions: **Edit** metadata (name, tags) and **Replace file** (upload a new PDF/text file using the same accepted types as `resumes.update_resume`/`_check_file`). Tickets and tailored files are untouched by replacement, as today.
- Success: `Resume saved.` / `Resume file replaced.` Invalid file: the existing validation message is shown. Empty name rejected: `Name cannot be empty.`
- Empty: `No resumes yet. Add one with 'hireember resume add'.`

### Loading and error states
- Initial load shows `Loading tickets...`; failures show `Could not load tickets. Retry` with a retry action. Server errors on saves show the message returned and keep the user's input.

## Acceptance criteria

- AC-1: For one ticket in each of the seven statuses, the board card, list row and detail panel show the status link with the label in Links above, or the exact text `No link available`. Skipped and closed tickets show the job posting link if one exists.
- AC-2: With N tickets in "blocked for human" (N may be 0), the tab heading and badge show N; the queue lists exactly those N tickets regardless of Tickets filters; each entry shows a non-empty reason and a next step from the mapping above; N=0 shows the empty message.
- AC-3: Manual status change, note and referral note each write one `ticket_events` row with actor `user`. Status change calls `tickets.set_status`, so the no-op on same status, invalid status rejection and duplicate rules apply unchanged. Notes and referral notes are stored in the new notes column(s) and the event row records which was saved (reason text `note` / `referral note`) and keeps the ticket's current status. Events appear in the history list after saving.
- AC-4: The CSV for a filtered view has the exact header in the CSV export section, one row per ticket in that view (in the displayed sort order), and parses with Python's standard `csv` reader with commas, double quotes and newlines in notes round-tripping unchanged (excluding the formula-guard prefix).
- AC-5: `hireember dashboard --host 0.0.0.0` exits non-zero with the refusal message and does not bind; default host is `127.0.0.1`; `--host 127.0.0.1` is accepted; any other host (including `localhost`, `::1`, LAN addresses) is refused with the same message.
- AC-6: With 5,000 tickets seeded, the list endpoint responds in under 2 seconds (unfiltered, sorted by default and by each sortable column, and with filters).
- AC-7: A status change written to the database (by code other than the dashboard) is delivered to an open dashboard through the update endpoint or stream within 5 seconds and without reload; the payload identifies the ticket and its new status.
- AC-8: Answers can be viewed, edited, merged (two entries into one) and deleted, and resumes' metadata edited and file replaced; after a page reload each change is shown; failed operations change nothing.
- AC-9: With the same company, score, date and resume filters, the board and the list contain the same set of tickets, and the column counts on the board sum to the list's row count.
- AC-10: `hireember dashboard` exists and starts the server; `hireember --help` lists it; `doctor` output and any other help or message listings that hard-code command names include it; existing tests that assert those listings are updated.

## Edge cases and errors
- Ticket with no company, title, location, score, resume or applied date: shown as `-` in UI, empty in CSV.
- Unscored ticket (score null) is excluded by any score filter and included when no score filter is set.
- Invalid filter values (non-numeric score, from-date after to-date): inline message `Enter a whole number from 0 to 100.` / `From date must be on or before To date.`; the previous results stay.
- Ticket deleted or changed between load and action: `This ticket changed. Reloaded.` and the panel refreshes.
- Same-status change: no event written, toast `Ticket is already <status>.`
- Concurrent edits from two tabs: last save wins; live update refreshes the other tab's notes unless that box is being edited.
- Notes with HTML or script content are displayed as plain text, never executed.
- Requests whose Host header is not `127.0.0.1` or localhost on the chosen port are rejected (protects against DNS rebinding); state-changing requests from other origins are rejected.
- Database locked by a running job: reads and writes retry briefly, then show `Database is busy. Try again.`
- Merge of answers whose normalized questions conflict: user chooses which text to keep; no silent choice.
- Deleting an answer that a queue item or ticket still references does not break those items.
- Large notes (> 10,000 chars) rejected: `Note is too long (max 10,000 characters).`
- CSV with 5,000 tickets completes within 5 seconds.

## Out of scope
- Drag-and-drop on the board.
- Authentication, multi-user, remote access, HTTPS.
- Changes to the apply runner or scoring logic.
- Replacing the Rich terminal view or `view.py`.
- Adding or deleting resumes and tickets from the dashboard; creating answers from scratch (only view, edit, merge, delete).
- Editing the ticket's company, title, or other job fields.

## Open questions
- Link to local tailored files: browsers will not open `file://` links from an `http://127.0.0.1` page. Spec shows the path with `Copy path`; alternatively the server could serve the files from the HireEmber data directory. Which is wanted?
- Default port 8765 and the command name `dashboard` are proposals; confirm or change.
- Should the Date filter apply to created date, applied date, or last-updated date? Spec uses applied date when set, otherwise created date.
- Does the existing schema store a session link for "applying" and tailored-file link per ticket? If not, the "No link available" text applies; tech-spec to confirm against `ticket_events.link`/`set_ticket_files`.
- Merge semantics: spec lets the user choose which question and answer text to keep; confirm that is acceptable versus automatic (keep newer).
