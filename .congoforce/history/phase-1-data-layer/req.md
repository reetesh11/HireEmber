---
class: feature
size: medium
title: Add ticket data layer, ApplyPilot migration and duplicate detection
---
# Requirements — Add ticket data layer, ApplyPilot migration and duplicate detection

## Problem
HireEmber tracks only one row per role in `jobs`. To support per-application tickets, human gates and duplicate protection, the SQLite store needs new tables, a safe migration of existing ApplyPilot databases (`applypilot.db` or `hireember.db`), ticket status history, and duplicate detection before any browser work. This phase is data layer only, with no UI.

## Requirements
- R1. When the database is initialised, the system shall create idempotently (`CREATE TABLE IF NOT EXISTS` / `ensure_columns`) the tables `companies`, `tickets`, `ticket_events`, `queue_items`, `answers`, `resumes`, `runs`, `settings`, and add company id, normalized title, normalized location and last seen to `jobs`, keeping every existing `jobs` row.
- R2. When a migration will change an existing database file, the system shall first copy that file to a backup file next to it.
- R3. When the migration runs, the system shall create one ticket for each `jobs` row that has been tailored or attempted, mapped from `apply_status` as follows, with an initial `ticket_events` row carrying the reason:
  - empty, tailored -> pending (no reason)
  - in_progress -> pending ("stale lock from an interrupted run")
  - applied -> applied ("unverified")
  - failed -> blocked for human (the stored error text)
  - manual -> blocked for human ("manual ATS")
  - captcha -> blocked for human ("CAPTCHA")
  - login_issue -> blocked for human ("account needed")
  - expired -> closed ("role expired")
- R4. When the migration runs again on an already migrated database, the system shall change nothing (same tables, tickets, events and `jobs` count).
- R5. When a role is scored, the system shall ensure exactly one ticket exists for it: pending if score >= threshold (setting default 7), otherwise skipped.
- R6. The system shall allow only the statuses pending, started, applying, blocked for human, applied, skipped, closed, and shall write a `ticket_events` row (status, actor system or user, reason, optional link and link kind, time) for every status change, returned in order as the ticket history.
- R7. When a ticket is asked to move to started, the system shall first look for another ticket with the same application URL, or the same lowercased company, normalized title and normalized location.
- R8. If the match is in started, applying, blocked for human or applied, then the system shall set the new ticket to blocked for human with reason "duplicate", store `duplicate-of` pointing at the existing ticket, and not move it to started.
- R9. Where the user overrides a duplicate block with a reason, the system shall let the ticket move on and record the override and reason in `ticket_events` with actor user.

## Acceptance criteria
- AC-1: Migrating a fixture ApplyPilot DB with at least one `jobs` row per old `apply_status` value (empty, tailored, in_progress, applied, failed, manual, captcha, login_issue, expired) creates all tables listed in R1, yields the status and reason per R3 for each, and leaves a backup file in the DB's directory.
- AC-2: Running the migration a second time leaves table list, ticket count, `ticket_events` count and `jobs` row count identical to after the first run, and the fixture works for both `applypilot.db` and `hireember.db` file names.
- AC-3: Scoring roles with scores 7 and 6 (default threshold 7) produces exactly one ticket each: pending and skipped respectively; re-scoring the same role does not create a second ticket.
- AC-4: After a sequence of status changes on one ticket, its history lists one event per change in order, each with time, actor and reason; an invalid status is rejected.
- AC-5: Two scored roles with the same company (case-insensitive), normalized title and location, or the same application URL, give a second ticket that is blocked for human with reason "duplicate" and `duplicate-of` set to the first; attempting to move it to started fails. A match whose ticket is only pending, skipped or closed does not block.
- AC-6: Overriding that block with reason "reapplying" lets the ticket move to started, and `ticket_events` holds the override with that reason and actor user.
- AC-7: Existing `jobs` behaviour (`init_db`, `store_jobs`, `get_stats`) still passes the current test suite.

## Out of scope
- Per-company and per-day limits (FR-DUP-4, phase 3).
- Dashboard views of tickets (phase 4).
- Populating resumes, answers and companies tables beyond creating them.

## Assumptions
- Title normalization (lowercase, trim, collapse whitespace and punctuation) and location normalization are defined by the implementation and applied to both new and migrated `jobs` rows.
- Backup is skipped when the DB file does not yet exist (fresh install), and is made on each migration run that changes an existing file; a no-op rerun may skip it.
- "Scored" means a `jobs` row with a fit score; the threshold is read from `settings` key with default 7.
- The user-facing "show the reason" for duplicates is met by the stored status reason and link in this phase.
- A migrated ticket needs no duplicate check, since it records history rather than starting work.

## Open questions
- none
