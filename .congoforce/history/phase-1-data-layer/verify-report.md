# Verify report — phase-1-data-layer

## Result
PASS — all seven acceptance criteria are met. Two major findings (not blocking) are worth fixing.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Migration creates the 8 tables, R3 status and reason per old apply_status, backup | met | migration.py `_STATUS_MAP`, `migrate_tickets`, `backup_if_needed`; test_p1_ac1_migration.py |
| AC-2 | Second run changes nothing; works for applypilot.db and hireember.db | met | `NOT EXISTS` guard plus `tickets.job_url UNIQUE`; `needs_migration` gives no second backup; test_p1_ac2_idempotent.py |
| AC-3 | Scores 7 and 6 give pending and skipped, one ticket each, no duplicate on rescore | met | tickets.py `_ensure_ticket`; scorer.py calls `set_job_score`; test_p1_ac3_scoring.py |
| AC-4 | Ordered history, invalid status rejected | met | `set_status`, `get_history`; test_p1_ac4_history.py |
| AC-5 | Duplicate blocks second ticket, blocked for human, duplicate-of set, start refused; non-blocking matches pass | met | `_find_duplicate`, `_BLOCKING_STATUSES`; test_p1_ac5_duplicates.py |
| AC-6 | Override with reason "reapplying" starts the ticket, with a user event | met | `set_status` override branch; test_p1_ac6_override.py |
| AC-7 | Existing init_db, store_jobs, get_stats unchanged | met | test_p1_ac7_unchanged.py; full suite 194 passed (checks.md) |

## Spec compliance
The code follows tech.md and its architecture diagram: init_db runs backup, then schema, then ensure_columns, then migrate_tickets, and the scorer calls `tickets.set_job_score`. Nothing built goes beyond the spec, apart from the optional `commit=False` parameter on `set_job_score`.

## Code quality
- Major, discovery/jobspy.py:183, workday.py:331 and smartextract.py:111: these insert paths do not set the new normalized columns or last_seen_at. After any such discovery run the next `init_db` treats the database as needing migration and writes a full backup, so backups accumulate on every start. Duplicate keys for those rows are missing until that backfill. Route these inserts through the same normalization, or exclude backfill-only NULLs from `needs_migration`.
- Major, tickets.py (`_ensure_ticket`, IntegrityError branch): `conn.rollback()` inside a batched `commit=False` scoring run discards earlier uncommitted scores. Use a savepoint, or re-select without rolling back.
- Note, tickets.py `set_status`: a ticket blocked as duplicate stays refused even if the original is later closed. It can only continue through an override.

## Recommendation
Ready for a human reviewer. Recommend fixing the two major findings, the backup growth in particular, before or soon after merge.
