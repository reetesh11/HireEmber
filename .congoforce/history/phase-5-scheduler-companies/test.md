# Acceptance test plan — Add scheduled runs, run summaries and a user-maintained company list

## Coverage
| Criterion | File | Test names (summary) | Red because |
| --- | --- | --- | --- |
| AC-1, AC-13 | `tests/acceptance/test_p5_scheduler.py` | parse_time, set/get/clear schedule, `test_scheduled_run_fires_once_at_set_time`, due_slot, serve once | `hireember.scheduler` missing |
| AC-2 | `test_p5_runs.py` (`test_overlapping_runs_produce_one_row`), `test_p5_scheduler.py` (`test_overlapping_scheduler_trigger_makes_no_row`), `test_p5_surfaces.py` (`test_post_stage_unknown_and_busy`) | one row on overlap | `hireember.runs` missing |
| AC-3 | `test_p5_scheduler.py` (`test_scheduled_run_never_applies_by_default`), `test_p5_runs.py` (`test_apply_not_called_when_off`) | apply stage callable never called | `runs`/`scheduler` missing |
| AC-4 | `test_p5_companies.py` (`test_discovery_stores_roles_with_all_fields`, `test_rediscovery_updates_last_seen_keeps_date_found`, `test_store_jobs_now_parameter_is_optional`) | fields stored, one record, last-seen updated | `hireember.companies` / `discovery.companies` missing; `store_jobs` has no `now` |
| AC-5 | `test_p5_companies.py` (`test_failing_source_logged_others_continue`, `test_all_sources_fail_run_still_ends`) | failure logged against source, others continue | modules missing |
| AC-6 | `test_p5_companies.py` (`test_add_remove_search_list`, `test_next_run_searches_added_and_skips_removed`, `test_cli_company_add_list_remove`) | add/remove effect and messages | no `company add/remove` |
| AC-7 | `test_p5_surfaces.py` (`test_help_exits_zero` for schedule, scheduler, export; top-level help); `test_p5_unchanged.py` (existing commands, expect_red false) | help exits 0 | new commands missing (exit 2) |
| AC-8 | `test_p5_runs.py` (`test_blocked_tickets_enter_queue_once`, `test_enqueue_blocked_defaults`) | N queue items with company, reason, page link, no duplicates | `runs.enqueue_blocked` missing |
| AC-9 | `test_p5_surfaces.py` (`test_runs_page_empty_state`, `test_runs_page_shows_counts_newest_first_and_escapes`, `test_api_runs`, `test_index_has_runs_tab_and_stage_buttons`) | `/runs` HTML contains counts | no `/runs` route, `create_server` has no `stages` |
| AC-10 | `test_p5_scheduler.py` (`test_missed_slots_start_exactly_one_run`, `test_readme_documents_scheduled_and_missed_runs`) | one run for several missed slots; README "Scheduled runs" section mentions missed and next start | scheduler missing; README lacks section |
| AC-11 | `test_p5_scheduler.py` (`test_scheduled_apply_respects_remaining_daily_limit`, `test_scheduled_apply_skipped_when_limit_reached`) | apply limit = limit minus today's submissions | scheduler missing |
| AC-12 | `test_p5_runs.py` (`test_run_stage_*`, `test_start_stage_async_*`), `test_p5_surfaces.py` (`test_cli_run_stage_rejected_when_run_in_progress`, `test_post_stage_starts_only_that_stage`) | only the named stage runs, result message, no runs row | `runs.run_stage` missing |
| AC-14 | `test_p5_surfaces.py` (`test_export_csv_header_and_rows`, `test_export_bad_directory_raises_and_writes_nothing`, `test_cli_export`) | CSV files, headers, rows | `hireember.export` missing |

## Approach
Tests use only the interface-contract surfaces: `runs.execute_run/run_stage/start_stage_async` with an injected `Stages` (a recording `Recorder` in `p5_helpers.py`), `scheduler.tick/serve` with explicit tz-aware `now` values as the test clock, `discover_companies` with injected adapters, `CliRunner` against `hireember.cli.app`, and the dashboard server via `create_server(..., stages=...)`. The lock is held in tests by running `execute_run` in a thread whose discover stage blocks on an event. Nothing under test is mocked; the browser launcher is never reached because the apply stage callable is injected and asserted uncalled. Every expected-red test fails today with ModuleNotFoundError, a missing CLI command (exit 2), a missing `now` kwarg, or the README lacking the section. `test_p5_unchanged.py` pins `--help` on existing commands (green now).

## Untestable criteria
- AC-3 (real browser launcher): tests assert the injected apply stage is never called in a scheduled run; the verifier should confirm by reading that only the apply stage reaches the launcher.

## Open questions
- Existing `test_hireember_ac4_cli.py` asserts the exact set of top-level commands, so it will fail once `schedule`, `scheduler` and `export` are added. It must be updated (it is not frozen by this stage) in the same change.
