---
class: feature
size: large
title: Add jobs by URL and apply to them
---
# Requirements — Add jobs by URL and apply to them

## Problem
The user finds job postings themselves and wants to give HireEmber a list of URLs and have it apply. Today `hireember apply --url` only works for a job already in the database with a tailored resume (`launcher.acquire_job`), and there is no CLI command or dashboard control to add a job from a URL.

## Requirements
- R1. When the user runs `hireember add-job URL [URL...]` or submits the dashboard "Add job URLs" box (one URL per line), the system shall create one job record per new URL.
- R2. When a URL is added, the system shall fetch the page and extract title, company, location and full description, using the existing enrich cascade for known ATS layouts (JSON-LD, Greenhouse, Lever, Ashby, Workday) and the AI extractor for unknown layouts.
- R3. When a URL is added, the system shall normalise it (remove tracking parameters) and compare it with existing jobs by URL and by `application_url`; if it matches, the system shall report "already added" and create no second record.
- R4. When a job is added by URL, the system shall set `strategy = 'manual'`, record and show its score, and not apply the title and location filters from phase 9 to it.
- R5. When a job is added, the system shall run enrich (skipped if the description was already extracted), score, tailor, cover letter and ticket, in that order, ending with the ticket `approved` or `blocked for human` with a reason.
- R6. Where `--apply` (CLI) or "Add and apply" (dashboard) is used, the system shall continue to the apply stage for only the jobs from this run; otherwise it shall stop at the ticket and launch no browser.
- R7. When applying these jobs, the system shall use the existing gate, rate limits, duplicate check, blocked-questions queue and review mode, with review mode as the default. Submitting without review shall need an explicit per-run option (`--no-review`), never a saved default.
- R8. If a URL cannot be fetched or parsed (login wall, blocked, 404, no description), then the system shall report a plain reason and create a ticket `blocked for human`; the user can supply the description text (dashboard field or `--text FILE`) to continue.
- R9. If a URL is not `http`/`https`, or resolves (including via redirect) to a local or private address, then the system shall refuse it with a reason before reading any response body.
- R10. When a run finishes, the system shall list per URL: added / already added / failed, ticket id, score and next step (CLI table; dashboard table).
- R11. If one URL fails, then the system shall continue with the others; while a run is active, the system shall refuse a second start (single-run lock).
- R12. When applying, the system shall follow `docs/safety.md` and the daily apply limit (`schedule_apply_limit`); unsupported ATS flows, logins and CAPTCHAs shall end as `blocked for human` with the reason.

## Acceptance criteria
- AC-1: `addjob.add_job_from_url(conn, url, *, fetch=..., extract=...)` returns an `AddResult` with `status` in {added, duplicate, failed}, `job_url`, `ticket_id`, `reason`. With injected fixture fetch/extract and no network, a fixture page for each of JSON-LD, Greenhouse, Lever, Ashby, Workday and an unknown layout yields title, company, location and description.
- AC-2: `utm_*`, `gh_src` and `source` parameters are removed; the same job added with different tracking parameters gives one job record and the second result is `duplicate` with reason "already added". A match on `application_url` is also `duplicate`.
- AC-3: The stored job row has `strategy = 'manual'`. A job with a title the phase 9 filters would exclude (for example a sales title) is not skipped, and the filter functions are not called for it (stub asserted).
- AC-4: `hireember add-job` without `--apply` makes no call to the launcher (stub asserted). With `--apply` the launcher is called for exactly the added job URLs and no others (not duplicates, not failures).
- AC-5: The apply call for these jobs runs `preflight` first and uses review mode unless `--no-review` is passed. A config or saved setting cannot turn review off for this path.
- AC-6: URLs with schemes `file`, `ftp` etc., and hosts that are localhost, 127.x, 10.x, 192.168.x, 172.16-31.x, link-local (169.254.x, IPv6 equivalents), or redirects ending at such addresses, are refused with a reason before any body is read. `http://localhost:8765/` yields `failed` with a reason.
- AC-7: A fixture 404 and a fixture login page each give `failed` with a distinct plain-language reason and a ticket `blocked for human` whose reason appears in the blocked queue.
- AC-8: Supplying description text for a blocked URL (`add-job URL --text FILE`, or the dashboard field) continues the pipeline through score, tailor, cover letter to a ticket status of `approved` or `blocked for human`.
- AC-9: `POST /api/jobs/add` accepts `{urls: [...], apply: bool}`, rejects more than 25 URLs and URLs above a length cap with a 4xx error, starts the run through the stage runner under the single-run lock (a second start is refused), and returns per-URL results via the status route.
- AC-10: In a run of three URLs where one fails, the other two are added with tickets, and the result table has three rows with statuses added, added, failed, each with ticket id, score and next step. The CLI prints this table.
- AC-11: A CAPTCHA fixture in the apply stage ends the ticket `blocked for human` with a reason, not failed silently. Daily limit semantics match `schedule_apply_limit`.
- AC-12: The dashboard has an "Add job URLs" box with "Add" and "Add and apply" buttons and shows progress and the results table (in an existing tab; see Assumptions).
- AC-13: Run logs for these jobs contain no API keys and no resume text above debug level (existing phase 6 scans still pass).
- AC-14: README has a new "Apply to jobs you found" section; the CLI reference and `docs/traceability.md` list the new command, endpoint and ACs. The CLI help in `typer.Typer(help=...)` and the callback docstring are both updated.

## Out of scope
- Browser extension or "send current tab" integration.
- Logging in to sites for the user; passwords are never stored.
- Bulk import from a spreadsheet.

## Assumptions
- Phase 9 (title and location filters) is not visible in `src/hireember` at the time of writing (no filter code found). R4 bypass applies to whatever filter hook phase 9 provides; if phase 9 is not merged first, the bypass is only a `strategy = 'manual'` marker that later filters must honour. This must be confirmed.
- `launcher.acquire_job` currently requires `tailored_resume_path`; the new flow reuses it after tailoring and does not change its behaviour for other callers.
- The dashboard control goes in an existing tab (Tickets) since there is no Jobs tab; the Runs tab shows progress.
- Defaults to review mode (open question 1 in the source) and applies even with a low score (question 3), with the score shown.
- URL length cap is 2048 characters.

## Suggested split
1. Add by URL core: `addjob.py`, URL normalisation, dedupe, SSRF guard, fetch/extract, `strategy='manual'`, failure tickets, `add-job` CLI without `--apply` (AC-1 to AC-3, AC-6, AC-7, AC-10, AC-13).
2. Pipeline and apply: stages after add, `--apply`, `--no-review`, `--text`, preflight, limits, CAPTCHA handling (AC-4, AC-5, AC-8, AC-11).
3. Dashboard and docs: `POST /api/jobs/add`, status route, UI box and table, README, CLI reference, traceability (AC-9, AC-12, AC-14).

## Open questions
- Should a pasted URL ever apply without the review gate by default, or always stop at review (spec default is review)?
- Which sites do you most expect to paste (LinkedIn needs a signed-in session, which is out of scope)?
- For a low-scoring manual job, should the app warn and ask before applying, or just apply?
- Is phase 9 merged first, and what is the name of its filter entry point?
