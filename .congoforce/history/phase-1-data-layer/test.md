# Acceptance test plan — Add ticket data layer, ApplyPilot migration and duplicate detection

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p1_ac1_migration.py` | tables_created_and_jobs_kept, tickets_status_and_first_event_reason_per_old_status, normalized_columns_filled_for_existing_rows, backup_file_next_to_db_with_original_rows, fresh_install_makes_no_backup, store_jobs_fills_normalized_columns_and_last_seen | `hireember.migration` / `hireember.tickets` do not exist; new columns and tables are missing |
| AC-2 | `tests/acceptance/test_p1_ac2_idempotent.py` | second_migration_is_a_no_op[applypilot.db, hireember.db] | `hireember.migration` missing |
| AC-3 | `tests/acceptance/test_p1_ac3_scoring.py` | 7/6 pending-skipped, rescoring, threshold setting, bad threshold fallback (2) | `hireember.tickets` missing |
| AC-4 | `tests/acceptance/test_p1_ac4_history.py` | ordered history, same status no-op, allowed statuses, invalid status, invalid actor/unknown ticket | `hireember.tickets` missing |
| AC-5 | `tests/acceptance/test_p1_ac5_duplicates.py` | blocking statuses (4), URL key, URL fallback, non-blocking (3), partial match (3), empty location, oldest linked, re-ask | `hireember.tickets` missing |
| AC-6 | `tests/acceptance/test_p1_ac6_override.py` | override starts, override after block, empty reason refused (2) | `hireember.tickets` missing |
| AC-7 | `tests/acceptance/test_p1_ac7_unchanged.py` | store_jobs insert/skip, get_stats and idempotent init_db | green today (expect_red false) |

## Approach
Tests use only the interface contract: `init_db`, `store_jobs`, `get_stats`, `migrate_database`, and the `hireember.tickets` functions and exceptions. A legacy ApplyPilot DB is built with plain `sqlite3` using the old `jobs` schema (helper `tests/acceptance/p1_helpers.py`, not a conftest). New-module imports happen inside tests/fixtures so each test fails individually with ImportError/ModuleNotFoundError (missing behaviour), not at collection. Jobs are created through `store_jobs` (with `job["company"]`) and scored via `set_job_score`; application URLs are set by a plain UPDATE on `jobs`. Connections are closed with `close_connection`.

## Untestable criteria
- none

## Open questions
- Written to the contract: the unknown-status migration and the backup-failure error path are not tested (not in acceptance criteria).
