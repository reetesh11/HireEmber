---
class: feature
size: medium
title: Filter discovery by target title and location, editable in the dashboard
---
# Requirements — Filter discovery by target title and location, editable in the dashboard

## Problem
Discovery stores roles the user never asked for (sales, program manager) and uses its own substring location matcher (`_location_ok` in `discovery/jobspy.py`, `workday.py`, `smartextract.py`) that ignores `location.accept_patterns` and matches inside words ("CA" in "Chicago"). `exclude_titles` is documented in `searches.example.yaml` but no code under `src/` reads it. Out-of-scope jobs are enriched and scored, and the user cannot see, edit or correct the rules. Target roles, hard-no titles and target locations must be editable in the app, with one source of truth.

## Source of truth (per key)
| Setting | Canonical file and key | Read by |
| --- | --- | --- |
| Target roles | `searches.yaml` `title_include` | discovery, scorer prompt, doctor |
| Hard-no titles | `searches.yaml` `title_exclude` (alias `exclude_titles`) | discovery, doctor |
| Target locations, rejects, remote | `searches.yaml` `location.accept_patterns`, `location.reject_patterns`, `locations[].remote` (old keys `location_accept`, `location_reject_non_remote` read as aliases) | `location.py` |
| Where the user lives | `profile.json` `personal.city`, `personal.province_state`, `personal.country` | `location.py` (already added to accept targets) |

No value is stored in two files. `location.py` already merges the `searches.yaml` block with the `profile.json` personal fields; the panel edits each key in its own file and never copies profile fields into `searches.yaml`. No `location.yaml` exists and none is added.

## Requirements
- R1. When a search config has `title_include` or `title_exclude` (alias `exclude_titles`), the system shall match entries case-insensitively as whole words or whole phrases.
- R2. While `title_include` is non-empty, the system shall keep a job only if its title matches an entry; while it is empty, only `title_exclude` applies.
- R3. When any discovery path (job boards, Workday, careers pages, company list) finds a job, the system shall apply the title filter and `location_skip_reason` before the job is stored as a normal job.
- R4. When a job is dropped, the system shall store it as `skipped` with reason `title: <matched term>` or `location: <text>`, so the URL is not fetched again.
- R5. The system shall read old and new location keys in one place with identical results, and shall not match a location entry inside another word.
- R6. When discovery finishes, the system shall report dropped counts by reason type plus a `hint` in the discover result, write them to the run log with up to 20 dropped titles, and show the counts in the Runs tab.
- R7. When the user restores a skipped job with a `title:` or `location:` reason, the system shall return it to `new` so enrich and score process it.
- R8. The dashboard shall have a Profile panel that reads target roles, hard-no titles, target locations, reject locations, remote flag and the personal city/region/country from the files above, and writes edits back to the same files.
- R9. When the user saves the Profile panel, the next discover run shall use the new values without restarting the server or app.
- R10. When `hireember init` runs, the system shall write `title_include` and `title_exclude` proposed from the resume and profile target role.
- R11. When scoring, the system shall put the `title_include` role family in the prompt and treat a job outside it as score 1-3 with reason "role family".
- R12. When `hireember doctor` runs, the system shall warn if a job-board query list exists with both title lists empty, and name unknown or unread config keys.

## Acceptance criteria
- AC-1: `title_filter(title, include, exclude)` in new `titles.py` returns a skip reason or `None`. `exclude=[sales, program manager]` drops "Senior Program Manager" and keeps "Backend Engineer"; `include=[engineer]` drops "Account Executive"; "sales" drops "Sales Engineer" by whole word; phrase, case and empty-list cases are tested.
- AC-2: Each discovery path (jobspy DataFrame, Workday response, careers page, company list) filters before insert and stores a `skipped` row with the reason; one fixture per path.
- AC-3: `_location_ok` is removed from the three discovery modules; no second location matcher exists under `discovery/`. An old-key config and a new-key config give identical keep/drop results.
- AC-4: Entry `CA` does not match "Chicago, IL" or "Vacation"; `SF` does not match "Transfer"; "Calgary, AB" still passes for target Canada.
- AC-5: The discover result has `dropped` counts by reason (for example "Dropped 34: 21 title, 13 location") and `hint` (phase 8 shape); the run log lists at most 20 dropped titles; the Runs tab shows the counts.
- AC-6: `POST /api/tickets/<id>/restore` (or equivalent in the existing API) moves a skipped ticket with a `title:`/`location:` reason to `new` and rejects other tickets with a clear error; Tickets rows show a Restore action for those reasons; a restored job is processed by enrich and score.
- AC-7: After init with a software-engineer fixture resume, `searches.yaml` has non-empty `title_include` and `title_exclude`, and the exclude list contains "sales" and "program manager".
- AC-8: A Profile API read returns the values from `searches.yaml` and `profile.json`; a write updates only the keys listed in the table, in their canonical file, and leaves other keys intact. Editing `exclude_titles` via the panel results in `title_exclude` being the stored key with no duplicate. A test shows a value saved through the panel is the value `location_skip_reason` and the title filter use on the very next call (no restart), and that a profile-panel country change is seen by `location.py`.
- AC-9: The Profile panel (index.html) lists, adds and removes keywords for roles, hard-no titles, accept and reject locations, plus the remote toggle and personal city/region/country; invalid input (non-string, blank, duplicate after case folding) is rejected with a message; a failed write leaves both files unchanged (atomic write).
- AC-10: With a stub model, the scorer prompt contains the `title_include` role family, and a "role family" reason yields a score at or below 3.
- AC-11: `hireember doctor` warns on a misspelt key such as `exclude_title`, and on a query list with both title lists empty.
- AC-12: Behaviour is unchanged for jobs passing both filters and for remote, empty and placeholder locations (phase 0e/0f); existing tests pass.
- AC-13: README search-config section, `searches.example.yaml` (only keys the code reads) and `docs/traceability.md` document the table above.

## Out of scope
- Salary filtering and company blocklists.
- Changing which job boards are searched.
- Geocoding or distance-based location matching.

## Assumptions
- Dropped jobs use the existing tickets table: status `skipped`, `status_reason` prefixed `title:` or `location:` (the `location:` prefix is already used by `database.py` stats).
- Dropped jobs are visible on request (skipped list and a counter), not in the default board view.
- No Profile panel exists in `web/static/index.html` today (tabs are Tickets, Blocked, Answers, Resumes, Runs), so this task adds it as a new Profile tab; the human's "existing profile panel" is read as this.
- Saving `searches.yaml` from the panel may drop YAML comments; accepted, since the file is rewritten from parsed data.
- Specific roles and exclusions are user data, not hard-coded; only init proposals ship as editable defaults. The user's own lists are entered through the panel.

## Open questions
- none
