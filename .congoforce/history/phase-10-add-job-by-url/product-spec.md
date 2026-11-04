# Product spec — Add jobs by URL and apply to them

## User-facing behaviour

### CLI: `hireember add-job`
```
hireember add-job URL [URL...] [--apply] [--no-review] [--text FILE]
```
- Without `--apply`: each URL is fetched, a job is created, and the job goes through enrich, score, tailor, cover letter and ticket. It stops at the ticket. No browser opens.
- `--apply`: after the ticket stage, the apply stage runs for only the jobs added in this run. Review mode is on: the browser stops before every submit.
- `--no-review`: valid only together with `--apply`. Submits without the review stop for this run only. It is never saved and never read from config or the environment. Without `--apply` it exits 2 with "--no-review needs --apply."
- `--text FILE`: the file holds the job description text. It is used instead of fetching the page, so it needs exactly one URL; with more than one URL the command exits 2 with "--text works with one URL at a time." It also applies to a URL that earlier ended `blocked for human` because the page could not be read; the pipeline continues from that job (see AC-8).
- With no URL the command prints the usage error (exit 2). Help text lists all options. The `typer.Typer(help=...)` text and the `main` callback docstring both mention adding jobs by URL.

Result table printed at the end (one row per URL, in the order given):

| URL | Result | Ticket | Score | Next step |
| --- | --- | --- | --- | --- |
| https://boards.greenhouse.io/acme/jobs/1 | added | #41 | 8 | Ready for review in the dashboard |
| https://jobs.lever.co/acme/2 | already added | #17 | 6 | Already in your tickets |
| https://example.com/careers/3 | failed | #42 | - | Blocked for human: page not found (404) |

- Result is one of `added`, `already added`, `failed`.
- Score is the 0-10 fit score, or `-` when none was computed. The score is shown even when low; a low score does not stop the job and does not ask for confirmation.
- Next step is a short sentence, for example "Stopped at ticket (run with --apply to apply)", "Applied after review", "Waiting at review", "Blocked for human: <reason>", "Already in your tickets".
- A summary line follows: `3 URLs: 2 added, 0 already added, 1 failed.`
- Exit code 0 if at least one URL was processed without a command error, even if some rows failed; exit 1 only if a run could not start (for example a run is already active). A URL refused before fetching (bad scheme, private address) is a `failed` row, not a command error.
- A run that is already active (CLI, scheduler or dashboard) is refused: "A run is already in progress. Wait for it to finish, then try again." Exit 1.
- URLs are de-duplicated within one command (same normalised URL given twice yields one row `added` and one `already added`).

### Dashboard
- The Tickets tab gets an "Add job URLs" panel above the board/list: a multi-line text box (one URL per line), an optional "Job description text (use if a page cannot be read)" field (shown with one URL only, see below), and two buttons: "Add" and "Add and apply".
- "Add" runs add-only. "Add and apply" runs with review mode on. The dashboard has no control to turn review off.
- Both buttons are disabled while a run is active, with the line "A run is in progress." Blank lines and surrounding spaces are ignored; at least one URL is required ("Enter at least one URL.").
- Client-side checks mirror the server: more than 25 URLs shows "You can add up to 25 URLs at a time."; a line longer than 2048 characters shows "A URL is longer than 2048 characters."
- Progress: the Runs tab shows the run as active (existing behaviour), and the panel shows "Adding 2 of 3..." updated by polling the status route.
- Results: when the run finishes, the panel shows the same table as the CLI (URL, Result, Ticket id linking to the ticket, Score, Next step). The table stays until the next run starts or the page is reloaded; the last result is also available from the status route.
- In the blocked queue (Blocked tab), a URL that could not be read appears with its reason, and the ticket drawer offers a "Paste job description" text field with a "Continue" button that supplies the text for that job and resumes the pipeline.
- Because the description field belongs to one job, the panel's own description field is used only when exactly one URL is entered; with several URLs it is hidden.

### API
- `POST /api/jobs/add` with `{"urls": ["..."], "apply": false}` (optional `"text": "..."`, only with a single URL). Success: `202 {"started": true}`. Errors use the existing `{error, code}` shape:
  - more than 25 URLs: `400`, "You can add up to 25 URLs at a time." (`too_many_urls`)
  - empty list or non-string items: `400`, "Enter at least one URL." (`invalid_urls`)
  - any URL over 2048 characters: `400`, "A URL is longer than 2048 characters." (`url_too_long`)
  - `text` with more than one URL: `400`
  - a run is already active: `409`, "A run is already in progress." (`busy`)
- There is no `review` field. The API cannot turn review off.
- Per-URL results are returned through the existing `GET /api/stages/status`, extended with a `results` list of `{url, status, ticket_id, score, reason, next_step}` for the last add-jobs run, in input order, plus `progress: {done, total}` while running.

### Docs
- README has a new section "Apply to jobs you found" with the CLI usage, the dashboard box, the review default and the `--no-review` warning, what happens when a page cannot be read, and the privacy note on what is fetched.
- CLI reference and `docs/traceability.md` list `add-job`, `POST /api/jobs/add` and AC-1 to AC-14.

## Acceptance criteria

- AC-1: `addjob.add_job_from_url(conn, url, *, fetch=..., extract=...)` returns an `AddResult` with `status` in {`added`, `duplicate`, `failed`}, `job_url` (the normalised URL), `ticket_id` (int, or None only when no ticket could be created), `reason` (plain-language string; empty for `added`). With injected fixture `fetch` and `extract` and no network, one fixture page each for JSON-LD, Greenhouse, Lever, Ashby, Workday and an unknown layout yields non-empty title, company, location and description. Known layouts use the existing enrich cascade; only the unknown layout calls `extract`. Tests make no network call.
- AC-2: The parameters `utm_*` (any name starting `utm_`), `gh_src` and `source` are removed; other parameters and their order are kept. Fragments are dropped, host is lower-cased and a trailing slash is ignored for comparison. Adding the same job twice with different tracking parameters gives one job row; the second result is `duplicate` with reason exactly "already added" and the existing ticket id. A URL matching an existing job's `application_url` (after the same normalisation) is also `duplicate`, "already added".
- AC-3: The stored job row has `strategy = 'manual'`. A job with a title the phase 9 filters would exclude (for example "Sales Manager") is stored, not skipped, and gets no `skipped` ticket. The phase 9 filter entry point (`JobFilter.reason` and `intake.store_filtered`/`mark_dropped`) is not called for it (stub asserted). Location filtering is likewise not applied.
- AC-4: `hireember add-job` without `--apply` makes no call to the launcher and opens no browser (stub asserted). With `--apply` the launcher is called for exactly the job URLs with result `added` in this run, in input order, and not for duplicates, failures or any other job in the database. If nothing was added, the apply stage is skipped with the line "Nothing new to apply to."
- AC-5: The apply call for these jobs runs `preflight` first; if preflight fails, no job is applied to and the output shows the preflight message and rows end "Stopped at ticket: <preflight problem>". Review mode is on unless `--no-review` is passed on that command. No config key, saved setting or environment variable can turn review off for this path, and `--no-review` is not persisted.
- AC-6: URLs whose scheme is not `http` or `https` (`file`, `ftp`, `javascript`, etc.) and hosts that are or resolve to localhost, loopback (127.x, ::1), 10.x, 192.168.x, 172.16-31.x, link-local (169.254.x, fe80::/10), unique-local (fc00::/7), 0.0.0.0 or the unspecified address are refused. Each redirect hop is re-checked, so a redirect ending at such an address is refused. Refusal happens before any response body is read. Result is `failed` with reasons such as "Only http and https links are supported." or "This address is on your own network or computer, so it was not fetched." `http://localhost:8765/` yields `failed` with the second reason.
- AC-7: A fixture 404 gives `failed` with reason "The page was not found (404)." A fixture login page gives `failed` with reason "The page needs you to sign in, so the description could not be read." The two reasons are different. Each creates a ticket with status `blocked for human` whose reason is the same text and appears in the blocked queue. Other plain reasons: "The site blocked the request." (403/429), "The page did not load in time." (timeout), "No job description was found on the page.", "The page could not be fetched." (other errors).
- AC-8: `add-job URL --text FILE` (CLI) and the dashboard "Paste job description" field supply the description for a URL. If the URL already has a `blocked for human` ticket from a failed fetch, the same job record is reused (not reported as duplicate); otherwise a new job is created with that text. The pipeline then continues through score, tailor and cover letter to a ticket status of `approved` or `blocked for human` with a reason. An empty or unreadable file fails with "The description file is empty." or "The description file could not be read." and changes nothing.
- AC-9: `POST /api/jobs/add` accepts `{urls: [...], apply: bool}`; more than 25 URLs, or any URL above 2048 characters, returns a 400 with the messages above. A valid request starts the run through the stage runner under the single-run lock and returns 202. A second start while running returns 409 and starts nothing. Per-URL results and progress are returned by `GET /api/stages/status`.
- AC-10: In a run of three URLs where the second fails, the other two are added with tickets. The result table has three rows with statuses `added`, `failed`, `added` (in input order), each with ticket id, score (`-` for the failed one) and next step. The CLI prints this table and the summary line `3 URLs: 2 added, 0 already added, 1 failed.`
- AC-11: A CAPTCHA fixture in the apply stage ends the ticket `blocked for human` with reason "A CAPTCHA needs you to solve it." (not failed silently, not retried). Unsupported ATS flows and sign-in walls end the same way with their own reasons. The daily limit follows `schedule_apply_limit` semantics: jobs beyond the limit are not applied, stay at the ticket, and the row's next step reads "Daily apply limit reached; will wait."
- AC-12: The Tickets tab has an "Add job URLs" box with "Add" and "Add and apply" buttons, shows progress while running, and shows the results table when finished (columns URL, Result, Ticket, Score, Next step). The box is keyboard-operable and labelled for screen readers; progress and errors are announced with `role="status"`/`role="alert"`.
- AC-13: Run logs for these jobs contain no API keys and no resume text at info level or above; page text and resume text appear, if at all, only at debug level. Existing phase 6 scans still pass.
- AC-14: README has a new "Apply to jobs you found" section. The CLI reference and `docs/traceability.md` list the new command, endpoint and ACs. The `typer.Typer(help=...)` text and the `main` callback docstring both mention adding jobs by URL.
- AC-15 (implied by R7/R11): The same normalised job is never applied to twice: if a job added by URL already has an applied ticket, the add result is `duplicate`, and the duplicate check in apply still runs for jobs found by other routes.
- AC-16 (implied by R3/R11): Within one run, the same URL listed twice produces one `added` and one `duplicate` row.

## Edge cases and errors
- Empty input, whitespace-only lines, duplicate lines: ignored or reported as above.
- Invalid URL text (no host, spaces, "not a url"): `failed`, "That is not a valid web address." No ticket is created for a string that is not a URL at all (ticket_id is `-`); a valid http(s) URL that cannot be read does get a blocked ticket.
- Refused URLs (AC-6) are `failed` and create a `blocked for human` ticket only if the URL is a well-formed http(s) address; non-http schemes get no ticket. (See open question 2.)
- LinkedIn URLs: existing apply refuses them ("LinkedIn job URLs are not supported"). Add-job returns `failed`, "LinkedIn links are not supported because they need a signed-in session." with no ticket.
- Slow page: fetch times out after a fixed limit; reason "The page did not load in time."
- Very large page: the body is read up to a size cap; text beyond it is ignored and the run continues.
- Extraction returns no title or no description: `failed`, "No job description was found on the page.", ticket `blocked for human`.
- Missing company or location: the job is added with those fields blank; they show as "-" in the UI.
- Low score: the job continues, the score is shown. No warning prompt.
- Ticket `blocked for human` after tailor or cover letter (for example no base resume): row result is `added`, next step "Blocked for human: <reason>".
- A run is active (CLI or dashboard): second start refused (CLI exit 1; API 409; buttons disabled).
- A failure on one URL never stops the others. An unexpected error on one URL is a `failed` row with "Something went wrong adding this link." and details only in the log.
- Offline: fetch failures give "The page could not be fetched."; the run continues.
- Dashboard reload mid-run: the panel shows current progress from the status route and the table when done.

## Out of scope
- Browser extension or "send current tab" integration.
- Logging in to sites for the user; passwords are never stored.
- Bulk import from a spreadsheet.
- Turning off review mode from the dashboard, config or a saved setting.
- Asking for confirmation or blocking on low scores.

## Open questions
1. Should the dashboard "Add and apply" apply immediately in this run, or only queue and stop at the review gate in the browser? Spec assumes review mode opens the browser, as the CLI does.
2. For URLs refused by the safety check (private address, bad scheme), should a `blocked for human` ticket be created (req R8/R9 are ambiguous: R8 says failed fetches get a ticket, R9 says refuse)? Spec assumes: well-formed http(s) URLs get a ticket, non-http schemes and malformed strings do not.
3. Should LinkedIn URLs be refused at add time (spec) or added so the user can paste the description with `--text`?
4. Where should the exact next-step wording and the "Paste job description" control live in the Blocked tab versus the ticket drawer (spec places it in the ticket drawer, listed from the Blocked tab)?
5. The `--text FILE` rule requires a single URL. Is that acceptable, or should it map files to URLs?
