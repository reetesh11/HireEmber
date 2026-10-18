# Acceptance test plan — Phase 2: profile, base resumes, answer bank, score/tailor gating

## Coverage
| Criterion | File | Test focus | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p2_ac1_init.py` | ten groups in order, headings, answers stored with source profile, blank re-asked, EEO skip stored, profile written, keep/change on rerun | `hireember.profile` and `run_profile_step` do not exist |
| AC-2 | `test_p2_ac2_match.py` | answered, unknown, conflict, identical values, single open queue item | `hireember.answers` missing |
| AC-3 | `test_p2_ac3_queue_answer.py` | answer queued question, resolve, resume to pending, usage count, error messages, CLI `queue` and `answers list` | `answers` module and CLI groups missing |
| AC-4 | `test_p2_ac4_storage_sensitive.py` | five stored fields, no `password` in `profile.example.json` and schema, sensitive questions queued, never stored | module missing; `profile.example.json` still has `personal.password` |
| AC-5 | `test_p2_ac5_resumes.py` | add/list/pin/unpin, errors, choose_resume, ticket resume id (pinned and best fit), CLI `resume` | `resumes`, `gating` missing |
| AC-6 | `test_p2_ac6_validator.py` | `validate_against_profile` reasons, retry limit blocks ticket with reason in history and `status` | function missing; `validate_json_fields` does not yet add the reasons |
| AC-7 | `test_p2_ac7_threshold.py` | below threshold skipped and untailored, exactly threshold passes, custom threshold, reason non-empty, no resume, LLM error | `gating` missing |
| AC-8 | `test_p2_ac8_pdfs.py` | ticket holds existing valid PDFs; `write_text_pdf` | `gating`, `write_text_pdf` missing |
| AC-9 | `test_p2_ac9_immutable.py` | submitted ticket paths and bytes unchanged after `update_resume` | `gating`, `resumes` missing |
| unchanged | `test_p2_unchanged.py` | phase 1 ticket-by-threshold, existing validator | green now (`expect_red: false`) |

## Approach
Tests use only the public surfaces in the interface contract with a real SQLite database from `init_db`. The LLM is faked by patching `get_client` in the scorer, tailor and cover_letter modules (the contract's fake LLM). Tailored JSON uses string skill values; project and employer headers are plain names so they do not depend on segment splitting. CLI tests use `isolated_db` and a widened `hireember.cli.console` so tables are not wrapped. Output files go to the default temp `HIREEMBER_DIR`; job titles carry a random suffix to keep file names distinct.

I edited one existing test: `tests/acceptance/test_hireember_ac4_cli.py` `COMMANDS` now also lists `answers`, `queue` and `resume` (the new command groups), since it asserts the exact command set. It is red until the groups exist. The implementer must commit it as it stands (the shared-file rule in the standards).

try-tests: PASS. Failures are missing modules/functions, plus two wrong-result cases (`profile.example.json` has a password; `validate_json_fields` lacks the new reasons).

## Untestable criteria
- AC-1 wiring of `run_wizard` to `run_profile_step` via `hireember init`: interactive across other steps. The verifier should check by reading code. `run_profile_step` itself is fully tested.

## Open questions
- Wrapping: if the implementation prints tables with its own `Console` rather than `hireember.cli.console`, long cells may wrap in captured output.
- The rerun keep/change prompt is assumed to go through the `ask` callable.
