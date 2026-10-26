---
class: feature
size: medium
title: Release hardening - logs, token totals, key scan, traceability and docs
---
# Requirements - Release hardening

## Problem
Before release, a new user must get from the README to a first scored role without editing code. The user also needs per-run and per-ticket logs, a model and token cost per ticket, proof that no API key is stored, a requirement-to-test traceability table, and current docs. Today `docs/traceability.md` lists only a handful of IDs, and `docs/safety.md` does not exist.

## Requirements
- R1. When a pipeline run starts, the system shall write a log file for that run.
- R2. When an application attempt runs for a ticket, the system shall write a log file for that ticket's attempt.
- R3. When the user opens the dashboard, the system shall link each run and each ticket page to its log.
- R4. When the system finishes a scoring, tailoring or applying stage for a ticket, the system shall record the model and the token counts for that stage.
- R5. When the user opens a ticket page, the system shall show the model and token totals for scoring, tailoring and applying.
- R6. The system shall send no telemetry and shall store no API key in the repository or the database; keys shall live only in a git-ignored `.env`.
- R7. The system shall keep `docs/traceability.md` mapping every FR, SAF and NFR ID in the requirements document to at least one passing test.
- R8. If an FR, SAF or NFR ID has no mapped test, then the test suite shall fail.
- R9. The system shall document setup to a first scored role in the README, the rules of section 7 in CONTRIBUTING and `docs/safety.md`, and that schedules do not fire while the machine sleeps.

## Acceptance criteria
- AC-1: After a run, a log file exists for the run. After an application attempt, a log file exists for that ticket. The dashboard run view and ticket page each contain a link that resolves to the matching log (HTTP 200 with the log text).
- AC-2: For a ticket with recorded scoring, tailoring and applying stages, the ticket page (and its API payload) shows the model name and the token totals for each of the three stages. A stage with no record shows an explicit empty value, not an error.
- AC-3: A test scans tracked repository files and a seeded database for API-key patterns (for example the Anthropic key prefix (`sk` then `-ant-`), `sk-` followed by 20 or more characters, `AIza`) and finds none. `.env` is matched by `.gitignore` (`git check-ignore .env` succeeds) and `.env.example` is not ignored.
- AC-4: `docs/traceability.md` has a row for every FR, SAF and NFR ID found in `OpenApply — Requirements Document.md`, and each row names an existing test file (and test name where given). A test fails when an ID from the requirements document is missing from the table or maps to a nonexistent test.
- AC-5: `README.md` has a setup section that goes from install through `init` to a first scored role without any code edit, and states that schedules do not fire while the machine sleeps. `CONTRIBUTING.md` and `docs/safety.md` exist and each covers the section 7 rules (including no LinkedIn, no auto-submit without the gate, and no telemetry), checked by a test for required headings or phrases.
- AC-6: No telemetry: a test finds no analytics or telemetry client import or outbound call in `src/hireember`.

## Out of scope
- New product features beyond logs, token display and docs.
- Cost in currency (only model and token counts are required).
- Rewriting existing tests, except to fill traceability gaps.
- Changing the scheduler to run during sleep.

## Assumptions
- Logs live in the HireEmber data folder (`HIREEMBER_DIR`), not the repo.
- Where a stage has no token data from the provider, it records zero and the model name.
- The requirements document's section 7 is the source for safety rules and the ID list.
- AC-6 is added to cover the "no telemetry" half of NFR-7, which the input's AC-3 does not test.
- The traceability table already has 16 lines; the work is to complete it for roughly 75 IDs, and gaps may need small new tests.

## Open questions
- Does the traceability test treat FR IDs marked as later or out of scope in the requirements document as exempt, or must every ID map to a passing test?
- How long should logs be kept (keep forever, or prune after N days)?
- If filling traceability uncovers FRs with no test, should this task write those tests or list them in `docs/parked-fixes.md`? Writing them could make this large.
