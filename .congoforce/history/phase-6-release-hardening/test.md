# Acceptance test plan — Release hardening: logs, token totals, key scan, traceability and docs

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 (logs) | `tests/acceptance/test_p6_logs.py` | `test_log_paths_follow_the_contract`, `test_write_line_*`, `test_read_log_of_a_missing_file_is_none`, `test_unwritable_log_folder_*`, `test_run_log_exists_*`, `test_each_run_writes_its_own_file`, `test_log_step_also_appends_to_the_attempt_log`, `test_apply_ticket_writes_an_attempt_log` | `hireember.logs` does not exist; runs and attempts write no files |
| AC-7 (retention) | `tests/acceptance/test_p6_logs.py` | `test_prune_logs_deletes_91_day_old_files_and_keeps_89_day_old_ones`, `test_prune_logs_honours_max_age_days_and_never_raises_without_a_folder`, `test_a_new_run_prunes_old_logs_and_keeps_its_records` | no `prune_logs`; `execute_run` prunes nothing |
| AC-1 (dashboard) | `tests/acceptance/test_p6_dashboard_logs.py` | log URL 200 and 404 tests, runs page link and "Log removed", `/api/runs` `log_url`, ticket page "Attempt n log", "No attempt log yet.", ticket API `logs`, fragment | no `/logs/...` or `/tickets/<id>` routes; 404 body is "Not found." not "Log not found."; no Log column |
| AC-2 | `tests/acceptance/test_p6_usage.py` | usage module tests, collector tests, LLM usage tests, scoring/tailoring/applying wiring, ticket page and API tests | `hireember.usage` and `stage_usage` do not exist; the ticket page and `usage` payload are missing |
| AC-3 | `tests/acceptance/test_p6_keys_telemetry.py` | key scan of tracked files and DB, scanner self-checks, `.env` ignore checks | green today: guards facts that must stay true |
| AC-6 | `tests/acceptance/test_p6_keys_telemetry.py` | `test_no_telemetry_client_is_imported_or_called_in_the_package`, `test_pyproject_lists_no_telemetry_dependency` | green today: no telemetry exists and must stay so |
| AC-4 | `tests/acceptance/test_p6_traceability.py` | `test_every_requirement_id_is_in_the_table_exempt_or_known_exceptions`, `test_each_id_appears_once_*`, `test_every_main_row_names_existing_test_files_and_test_names`, `test_known_exceptions_*`, `test_exempt_ids_*` | the table has 6 of 75 IDs; no `## Exempt` or `## Known exceptions` sections |
| AC-5 | `tests/acceptance/test_p6_docs.py` | README setup and sleep tests, safety docs tests | no setup heading or sleep sentence; no `docs/safety.md`; no "Safety rules" in CONTRIBUTING |
| Unchanged | `tests/acceptance/test_p6_unchanged.py` | `/api/runs` fields, ticket API fields, empty runs page, `run_log` rows, `chat()` returns text, `attempt_log` rows, run and attempt continue with an unwritable log folder | green today and after |

## Approach
- Public surfaces only: `hireember.logs`, `hireember.usage`, `runs.execute_run`, `runs.log_event`, `apply.attempts.log_step`, `apply.runner.apply_ticket`, `gating.score_job_for_ticket`, `gating.tailor_ticket`, `apply.launcher.run_job`, `LLMClient.chat`, and the dashboard over real HTTP on 127.0.0.1.
- Logs are redirected with `monkeypatch.setattr(hireember.config, "LOG_DIR", tmp)`, as the contract allows.
- LLM calls use a real `LLMClient` whose HTTP layer (`_client`) is replaced by a stub that returns OpenAI-style JSON with `usage`. The scorer, tailor and cover-letter modules get this client through the same `get_client` hook earlier phases already patch.
- `run_job` runs against a fake `subprocess.Popen` that streams a `result` event (or nothing). `prompt.build_prompt` is patched to a stub because it needs a full profile; it is not part of this feature.
- The key scan builds its patterns from fragments so it does not match itself, and a self-check proves the scanner detects a planted key.
- Traceability reads `OpenApply — Requirements Document.md` from the repo root. It was untracked in the main checkout; I copied it into the worktree (untracked) so the tests run. The implementer must `git add` it, otherwise the traceability tests fail in a clean checkout.
- Exempt IDs are checked against the requirements document: the ID's line must contain "out of scope", "later release" or "deferred". The document marks no FR, SAF or NFR that way today, so the Exempt section is expected to be empty (the section and header must still exist).
- Red-for-the-right-reason check: with throwaway stand-ins for `logs` and `usage`, the wiring tests failed on their own assertions (for example `None == {...}`), not on setup errors. The stand-ins were removed.

## Untestable criteria
- none

## Open questions
- `OpenApply — Requirements Document.md` and `docs/parked-fixes.md` are untracked in the main checkout, so the worktree branch lacks them. The implementer must commit the requirements document and create or extend `docs/parked-fixes.md` with a `## Traceability known exceptions` section.
