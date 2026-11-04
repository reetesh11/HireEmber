# Product spec: Filter discovery by target title and location, editable in the dashboard

## User-facing behaviour

### Existing surface this builds on
- Dashboard (`src/hireember/web/static/index.html`) has tabs Tickets, Blocked, Answers, Resumes, Runs. This task adds a sixth tab, **Profile**. The `?tab=` URL parameter accepts `profile`.
- Tickets rows are shown with the existing statuses (`skipped` among them). Runs tab is rendered from `/runs?fragment=1`. API handlers live in `src/hireember/web/server.py`.
- CLI: `hireember init` and `hireember doctor` exist; discover results already follow the phase 8 shape (counts plus `hint`).

### Where each setting lives (one source of truth, no copies)
| Setting | File and key |
| --- | --- |
| Target roles | `searches.yaml` `title_include` |
| Hard-no titles | `searches.yaml` `title_exclude` (alias `exclude_titles`) |
| Target locations / rejected locations / remote | `searches.yaml` `location.accept_patterns`, `location.reject_patterns`, `locations[].remote` (old keys `location_accept`, `location_reject_non_remote` still read) |
| City, region, country | `profile.json` `personal.city`, `personal.province_state`, `personal.country` |

The Profile tab reads from and writes to exactly these places. Nothing is copied between files. The user never has to edit a file by hand to change these rules.

### Profile tab
Sections, top to bottom:
1. **Target roles**: keyword chips (title_include) with an input and "Add" button. Helper text: "Only jobs whose title contains one of these are kept. Leave empty to keep all titles except the ones below."
2. **Hard-no titles**: keyword chips (title_exclude). Helper text: "Jobs whose title contains one of these are dropped."
3. **Target locations**: chips (accept_patterns), plus a **Remote jobs accepted** checkbox.
4. **Rejected locations**: chips (reject_patterns).
5. **Where I live**: three text fields: City, Region/State/Province, Country.
6. A **Save** button (disabled until something changes) and a status line: "Saved. The next discover run will use these values." on success.

Behaviour:
- Each chip has a remove control (label "Remove <term>"). Add by button or Enter. Nothing is written until Save.
- Save sends the whole panel; only the keys in the table above are changed. Other keys in both files, including unrelated `searches.yaml` settings, are left intact. YAML comments in `searches.yaml` may be lost (accepted).
- If the file used `exclude_titles`, after Save the stored key is `title_exclude` and `exclude_titles` is gone. Same for old location keys: after Save the values are stored under the new `location` block, with no duplicate old key left.
- Loading state: "Loading profile..." until the read returns. Read failure: "Could not load profile." with a Retry button.
- Matching hint shown under the roles section: "Matches whole words or phrases, ignoring case. 'sales' matches 'Sales Engineer' but not 'Salesforce Developer'."
- Changes take effect on the next discover run and the next score; no restart of the server or app.

### Discovery
- Every discovery path (job boards, Workday, careers pages, company list) applies the title filter, then `location_skip_reason`, before a job is stored as a normal job.
- A dropped job is stored as a ticket with status `skipped` and reason `title: <matched term>` (for include-list misses: `title: not in target roles`) or `location: <text>`. The same URL is not fetched again.
- A dropped job is not enriched, scored or tailored.
- Jobs that pass both filters, and jobs with remote, empty or placeholder locations, behave exactly as before.

### Discover result, run log, Runs tab
- Discover result gains `dropped` (counts by reason type, e.g. `{"title": 21, "location": 13}`) and a `hint`. Example hint: "Dropped 34: 21 title, 13 location. Review them in Tickets (skipped) or edit rules in Profile." When nothing is dropped: no dropped line, `dropped` is `{"title": 0, "location": 0}`.
- The run log gets one summary line "Dropped 34: 21 title, 13 location" plus up to 20 lines "dropped: <job title> (<reason>)". If more than 20, a final line "...and N more".
- The Runs tab shows the counts for each run, in the form "Dropped 34 (21 title, 13 location)", next to the existing counts. Runs from before this change show nothing.

### Tickets: restore
- Skipped rows whose reason starts with `title:` or `location:` show a **Restore** button. Other skipped rows (for example "score 4 below threshold 6") do not.
- Restore moves the ticket back to the pipeline's initial status (`new` in the requirements) and clears the drop reason. Enrich and score then process it on the next run. A restored job is not dropped again by the same filter on later discover runs (restore is sticky for that URL).
- Dropped jobs are not in the default board view; they appear when the user filters by status `skipped`. The existing location-skipped counter now also counts title drops under their own label.

### Init
- `hireember init` writes non-empty `title_include` (from the resume and profile target role) and `title_exclude` to `searches.yaml`. For a software-engineer profile the exclude list includes "sales" and "program manager". The final init summary says: "Proposed target roles and hard-no titles. Edit them in the dashboard Profile tab." Existing user lists are not overwritten on re-run.

### Scorer
- The scoring prompt contains the `title_include` role family. A job outside it gets score 1-3 with reason text "role family", whatever the skill overlap. With `title_include` empty, no role-family line is added.

### Doctor
- `hireember doctor` prints a warning "Job-board queries are set but title_include and title_exclude are both empty; discovery will keep every title." when applicable.
- For each unknown or unread key, a warning of the form "Unknown config key 'exclude_title' in searches.yaml (not read by any code). Did you mean 'title_exclude'?" The suggestion is given only if a close match exists.

## Acceptance criteria
- AC-1: `title_filter(title, include, exclude)` in `src/hireember/titles.py` returns a reason string or `None`.
  - Reason formats: `title: <matched exclude term>`; `title: not in target roles` when include is non-empty and nothing matches. Exclude is checked first.
  - `exclude=["sales","program manager"]` drops "Senior Program Manager" (`title: program manager`), keeps "Backend Engineer". "Sales Engineer" is dropped by `sales`. "Salesforce Developer" is not dropped by `sales`.
  - `include=["engineer"]` drops "Account Executive", keeps "Software Engineer II".
  - Matching ignores case; punctuation/hyphens/slashes count as word boundaries ("Sales/Marketing Lead" matches `sales`); multiple spaces are collapsed in phrases.
  - Both lists empty returns `None`. Whitespace-only or non-string entries are ignored.
- AC-2: Jobspy DataFrame, Workday response, careers page and company-list paths each filter before insert, with one fixture per path. Each fixture asserts: the excluded job has status `skipped` and reason starting `title:` or `location:`; the kept job is stored normally; no skipped job is fetched/enriched on a second run.
- AC-3: `_location_ok` no longer exists in `jobspy.py`, `workday.py`, `smartextract.py`; no other location matcher exists under `discovery/`. A config with `location_accept` / `location_reject_non_remote` and an equivalent config with `location.accept_patterns` / `location.reject_patterns` give identical keep/drop results on a shared set of sample locations. If both styles are present, the new block wins.
- AC-4: Entry `CA` does not match "Chicago, IL" or "Vacation" (but matches "Toronto, CA" and "Oakland, CA"). Entry `SF` does not match "Transfer" (matches "SF Bay Area"). "Calgary, AB" passes for target Canada. Phase 0f rules are otherwise unchanged.
- AC-5: The discover result has `dropped` by reason type and a `hint`, for example "Dropped 34: 21 title, 13 location". The run log lists at most 20 dropped titles, then "...and N more". The Runs tab shows the counts per run.
- AC-6: `POST /api/tickets/<id>/restore`:
  - 200 with the updated ticket (status back to the initial pipeline status, drop reason cleared) for a skipped ticket whose reason starts `title:` or `location:`.
  - 409 with message "Only jobs dropped by the title or location filter can be restored." for any other ticket.
  - 404 for an unknown id, in the existing error JSON shape.
  - Tickets rows show **Restore** only for those reasons; after click the row leaves the skipped list. A restored job is picked up by enrich and score.
- AC-7: After init with a software-engineer fixture resume, `searches.yaml` has non-empty `title_include` and `title_exclude`, and the exclude list contains "sales" and "program manager". The Profile tab shows those lists, a saved edit is stored in `searches.yaml`, and the next discover run uses it without restart (see AC-8). (Added by gate 1 revision.)
- AC-8: Profile API read (`GET /api/profile`) returns `{"title_include": [...], "title_exclude": [...], "location_accept": [...], "location_reject": [...], "remote": bool, "personal": {"city","province_state","country"}}` taken from the canonical files (aliases and old keys normalised on read). Write (`PUT /api/profile`) updates only those keys, each in its canonical file, and leaves all other keys intact. Saving an `exclude_titles` config stores `title_exclude` only, with no duplicate. A test shows a saved value is what `location_skip_reason` and `title_filter` use on the very next call without restart, and that a changed country is seen by `location.py`. Success response is the re-read profile.
- AC-9: The Profile tab lists, adds and removes keywords for roles, hard-no titles, accept and reject locations, and has the remote toggle and city/region/country fields. Validation messages (shown inline, next to the field, nothing written):
  - non-string: "Enter text."
  - blank/whitespace: "Enter a keyword."
  - duplicate after case folding: "'<term>' is already in the list."
  - A failed write (API 4xx/5xx) shows "Could not save: <reason>. Nothing was changed." and leaves both files byte-identical (write to temp file then replace; if the second file fails, the first is not changed).
  - The server enforces the same rules; it returns 400 with the message.
- AC-10: With a stub model, the scorer prompt contains the `title_include` role family, and a response with reason "role family" results in a stored score of at most 3.
- AC-11: `hireember doctor` warns on a misspelt key such as `exclude_title` (naming the key and file) and on a job-board query list with both title lists empty. With a clean config, neither warning appears.
- AC-12: Behaviour is unchanged for jobs passing both filters and for remote, empty and placeholder locations (phase 0e/0f); the existing tests pass.
- AC-13: README search-config section, `searches.example.yaml` (only keys the code reads) and `docs/traceability.md` document the table above, the Profile tab, and the Restore action.

## Edge cases and errors
- `searches.yaml` missing: Profile read returns empty lists and `remote` false; a save creates the file with only the saved keys. `profile.json` missing: personal fields are empty; saving creates it or reports a clear error rather than corrupting anything.
- Malformed YAML/JSON on read: Profile tab shows "Could not read searches.yaml: <parse error>" and disables Save, so a hand-edited broken file is never overwritten.
- Include list non-empty and a job with an empty title: dropped as `title: not in target roles`.
- Job matches both include and exclude: exclude wins.
- Same entry in include and exclude is allowed (no cross-list rejection).
- Entries longer than 80 characters are rejected: "Keep entries under 80 characters."
- Discovery running during a save: the run uses either the old or the new values in full, never a half-written file.
- Concurrent restore of an already-restored ticket: second call returns 409 as above.
- Whole discover run drops everything: result hint still shows counts and adds "Check your target roles and locations in Profile."
- Unknown location format (empty or placeholder, e.g. "N/A"): kept, as in phase 0e/0f.

## Out of scope
- Salary filtering and company blocklists.
- Changing which job boards are searched.
- Geocoding or distance-based location matching.
- Preserving YAML comments on save.
- A separate `location.yaml`.

## Open questions
- Status naming: requirements say restored jobs return to `new`, but `tickets.py` lists statuses `pending, started, applying, blocked for human, applied, skipped, closed`. Spec assumes restore returns the ticket to whatever the first pipeline status is (shown as `pending` in the UI) unless tech-spec finds `new` is a separate stage value. Human to confirm only if the two differ.
- Restore stickiness (restored URL not dropped again by later discover runs) is implied by "so the URL is not fetched again" and R7 but not stated; spec assumes yes.
