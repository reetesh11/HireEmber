# Acceptance test plan — Rework the apply stage with human gates and safety rules

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p3_ac1_gates.py` | `test_gate_blocks_ticket_and_queues_item` (4 cases), `test_password_typed_field_never_gets_a_value`, `test_sensitive_question_text_is_blocked_even_for_a_text_field`, `test_asking_the_same_unknown_question_twice_queues_it_once` | `hireember.apply.runner` and `hireember.apply.session` do not exist |
| AC-2 | `test_p3_ac2_bank_fill.py` | `test_next_form_is_filled_from_bank_and_log_names_the_entry`, `test_profile_values_are_filled_and_logged_as_profile_source`, `test_every_filled_field_in_the_log_has_a_source`, `test_ticket_log_command_shows_the_source`, `test_ticket_log_command_handles_empty_and_unknown_tickets` | no runner, session, attempts module or `ticket log` command |
| AC-3 | `test_p3_ac3_duplicate.py` | `test_apply_ticket_returns_duplicate_without_calling_the_agent`, `test_worker_loop_never_launches_chrome_or_claude_for_a_duplicate` | no `apply_ticket`; the worker loop has no duplicate gate |
| AC-4 | `test_p3_ac4_outcome_unknown.py` | seven tests: kill after submit, `KeyboardInterrupt`, never picked again, before-submit interruption, two stale-recovery cases, no-op recovery | no `apply_ticket`, `GateSession` or `recover_stale_tickets` |
| AC-5 | `test_p3_ac5_injection.py` | `test_injected_instruction_changes_nothing_and_is_logged`, `test_note_page_text_reports_only_instructions` | no `GateSession.note_page_text` |
| AC-6 | `test_p3_ac6_removal.py` | repo scan, doctor names, prompt text, MCP config and tool list, gate server tools and `call_tool` | CapSolver still in `src/`, README, `.env.example`; prompt and launcher unchanged; no `gate_server`, `build_mcp_config` or `agent_tools` |
| AC-7 | `test_p3_ac7_confirmation.py` | four tests: link stored, unverified, blank link, no applied ticket lacks both | no session `submitted()`; no `confirmation_link` column |
| AC-8 | `test_p3_ac8_profile_limits.py` | profile refusal (unit, worker dirs, CLI), 4th open ticket held, one-day same-company wait, daily limit, defaults | no `DefaultProfileError`, `check_worker_profiles`, `limits` module |
| AC-9 | `test_p3_ac9_account_resume.py` | sign-in block, `ready` and resume, live session link, kind guards, CLI `queue ready`/`list`, `outcome unknown` to pending | no `ready_queue_item`, `resume_from`, `session_link`, `queue ready` command |
| AC-10 | `test_p3_ac10_closed_manual.py` | closed role, not retried, default close reason, manual company, flag cleared, unknown company, `company` commands | no `closed()`, `set_company_manual`, `is_manual_company`, `company` command |
| AC-11 | `test_p3_ac11_upload_review.py` | upload name, resume path, missing resume, review on, review setting and override, default off, ready after review | no `resume_path()`, `before_submit()`, review setting |
| Unchanged | `test_p3_unchanged.py` | job without ticket row acquirable, `apply --help` options, `queue answer` | passes before and after |

## Approach
Acceptance tests use only the interface contract. The "agent" is a Python function (`drive` in `tests/acceptance/p3_helpers.py`) that fetches a local fixture form from the 127.0.0.1 test server (`fixture_form_server`), parses fields with the standard library, and calls `GateSession` the way the real agent is told to: `note_page_text`, `answer_field`, `resume_path`, `stop`, `closed`, `before_submit`, `submit_pressed`, `submitted`. It is passed to `apply_ticket(conn, ticket_id, agent, ...)`. No Claude, Chrome or network is used. Fixture pages live in `tests/fixtures/forms/` (`known_form`, `password_field`, `captcha`, `unknown_question`, `account_wall`, `closed_role`, `injected`, `clean`, `upload_form`). Tickets are created with the phase 1 helper `add_job` plus tailored resume files; the profile is a temporary `profile.json` set through `config.PROFILE_PATH`. The `env` fixture is defined in each file on top of the `isolated_db` fixture, so CLI commands and `launcher.acquire_job` see the same database. Time-dependent limits use the real clock with generous windows or the `now` argument of `check_limits` and `eligible_ticket_ids`.

The existing `test_ac6_doctor.py` is edited: the `CapSolver API key` entry is removed from its expected check list (the standards note on editing existing tests applies). It is not listed in tests.json because 11 of its 12 tests already pass; the doctor part of AC-6 is covered by `test_doctor_has_no_capsolver_check` and, once the check is gone, by that file's one remaining red test (`test_run_checks_returns_all_checks_in_cli_order`).

## Untestable criteria
- AC-6 (runtime part): the real stdio JSON-RPC transport of the gate server and the tool list Claude Code actually receives. Tests cover `build_mcp_config`, `agent_tools()`, `TOOLS` and `call_tool`; the verifier reads the transport code.

## Open questions
- The contract does not give the profile source key (`profile:<key>`); tests only require the `profile:` prefix.
- The contract's profile mapping is "full name, email, phone"; tests use the questions `Full name` and `Email`.
- Tests were written by the same agent that wrote the tech spec, from the interface contract and product spec only (human choice; no separate agent was available).
