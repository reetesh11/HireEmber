---
class: feature
size: large
title: Add scheduled runs, run summaries and a user-maintained company list
---
# Requirements — Add scheduled runs, run summaries and a user-maintained company list

## Problem
Today the only unattended mode is `hireember apply --continuous`, a polling loop. Users want discovery, scoring and tailoring to run on a schedule they set, with a per-run summary on the dashboard, and blocked tickets surfaced in the action queue. They also need to maintain a company list (name, careers URL, ATS type) that decides what discovery searches. The repo has only a `company` command group (`manual`, `list`), a bundled `config/employers.yaml`, and `answers` and `queue` groups; there is no `schedule` or `export` command and no `runs` table.

## Requirements
- R1. When the user sets a schedule, the system shall start a run (discovery, scoring, tailoring) at the set time without the dashboard open.
- R2. When a run ends, the system shall write one `runs` row with counts of roles found, scored, skipped, tickets created and tickets blocked, and show it on the dashboard.
- R3. While a run is in progress, the system shall not start another; overlapping triggers shall produce one `runs` row.
- R4. Where scheduled applying is on, the system shall also apply to eligible tickets within the per-day limit; where it is off, the system shall never launch a browser during a scheduled run.
- R5. When the user starts a single stage from the CLI or dashboard, the system shall run only that stage and report its result.
- R6. When a run creates tickets that need a human, the system shall add each to the action queue with company name, reason and page link.
- R7. When discovery runs, the system shall search the companies in the company list and store each role with company, title, location, source, URL and date found.
- R8. When a role is found again, the system shall update its last-seen time and not create a second record.
- R9. If a source fails, then the system shall log the failure against that source and continue with the others.
- R10. When the user adds or removes a company (name, careers URL, ATS type), the system shall search the changed list on the next run.
- R11. When a scheduled run was missed while the machine was asleep or off, the system shall run it at the next start, and the README shall say so.
- R12. The system shall provide `schedule`, `export` and `answers` commands alongside the existing ones, and every command shall print help on a fresh install.

## Acceptance criteria
- AC-1: On a test clock, a scheduled run starts at the set time and writes exactly one `runs` row containing found, scored, skipped, tickets created and tickets blocked counts.
- AC-2: Two overlapping triggers produce one `runs` row.
- AC-3: With scheduled applying off, no browser is launched during a scheduled run (browser launcher is not called).
- AC-4: Discovery over a three-company fixture list stores roles with company, title, location, source, URL and date found. A second run leaves one record per role with an updated last-seen time.
- AC-5: A failing source is logged against that source in the run log and the other sources still run.
- AC-6: Adding a company makes the next run search it; removing one makes the next run skip it.
- AC-7: `hireember schedule --help`, `export --help` and `answers --help` exit 0, and `--help` exits 0 for init, run, apply, status, dashboard and doctor.
- AC-8: After a run that blocks N tickets, the queue lists N new items, each with company name, reason and page link.
- AC-9: The dashboard HTML contains each run's summary counts.
- AC-10: A run missed while the machine was off starts once at the next start (test clock), and the README documents this.
- AC-11: With scheduled applying on, a scheduled run applies only to eligible tickets and no more than the per-day limit.
- AC-12: Each stage (discover, score, tailor, apply) can be started alone from the CLI and reports its result; running one stage does not run the others.

## Out of scope
- Shipping a large employer list: only a small example `employers.yaml` ships (Q10).
- Phase 4 work.
- New ATS adapters beyond those already in `discovery/`.

## Assumptions
- `export` writes the user's data (tickets/runs) to a file; its exact format is a design choice for the tech spec, and `answers` already exists as a command group and stays.
- OS scheduler versus built-in loop is decided in the tech spec.
- Missed-run catch-up is one run, not one per missed slot.
- A run that was in progress when the process died does not block future runs forever (stale lock handling is a tech-spec detail).

## Suggested split
1. Run model: `runs` table, run summary, single-run lock, on-demand stages, dashboard summary, blocked tickets to queue (AC-1 partial, 2, 8, 9, 12).
2. Company list: discovery over the list, upsert with last-seen, per-source failure logging, add/remove commands, example `employers.yaml` (AC-4, 5, 6).
3. Scheduler: `schedule` command, scheduled applying switch and per-day limit, missed-run catch-up, `export` command, help on all commands, README (AC-1, 3, 7, 10, 11).

## Open questions
- What should `export` export (tickets, runs, answers) and in what format (CSV, JSON)?
- Should the user be able to choose the schedule as a cron expression, a daily time, or an interval?
