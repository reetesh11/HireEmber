# Acceptance test plan — Resume library with .docx upload and local searchable context store

## Coverage
| Criterion | File | Tests | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p7_ac1_upload_api.py` | 25 (txt/docx/pdf via raw and multipart, bad extension, empty, exactly 10 MB, over 10 MB, 413, blank name, duplicate, validation order) | `POST /api/resumes` does not exist (404) |
| AC-2 | `tests/acceptance/test_p7_ac2_ui_form.py` | 3 (form controls, upload states and toast, empty-state text) | the page has no Add resume form and the old empty-state text |
| AC-3 | `tests/acceptance/test_p7_ac3_docx_cli.py` | 8 (CLI docx, corrupt docx, unsupported, help texts, `extract_docx_text`, dependency) | `.docx` is rejected, `extract_docx_text` is missing, help is old, no python-docx |
| AC-4 | `tests/acceptance/test_p7_ac4_extraction.py` | 16 | `hireember.resume_index` and extraction on add do not exist |
| AC-5 | `tests/acceptance/test_p7_ac5_store.py` | 3 | no `resume_chunks` table or FTS5 index |
| AC-6 | `tests/acceptance/test_p7_ac6_search.py` | 31 | `resumes.search` does not exist |
| AC-7 | `tests/acceptance/test_p7_ac7_prompts.py` | 11 | `context_block` and the `resume_context` parameters do not exist |
| AC-8 | `tests/acceptance/test_p7_ac8_status.py` | 14 | no status fields, `extract_resume` or `/extract` route |
| AC-9 | `tests/acceptance/test_p7_ac9_delete.py` | 10 | no `delete_resume`, DELETE route or `resume delete` |
| AC-10 | `tests/acceptance/test_p7_ac10_sanitise_logging.py` | 15 | `add_resume_bytes` and the upload route do not exist |
| AC-11 | `tests/acceptance/test_p7_ac11_unchanged.py` | 7 (green now, `expect_red: false`) | not red: pins uniqueness, pin/unpin/choose, `get_resume_text` and byte-identical prompts for a chunkless resume |
| AC-12 | `tests/acceptance/test_p7_ac12_docs.py` | 10 | README has no privacy note, traceability has no standalone RES-1..RES-7 rows |

`tests/acceptance/p7_helpers.py` is a shared helper (minimal `.docx` built with zipfile, blank PDF via pypdf, multipart builder, tolerant raw POST), not a test file.

## Approach
Tests use only the interface contract: `hireember.resumes`, `hireember.resume_index`, `hireember.resume_extract`, the scorer/tailor/prompt hooks, the Typer `app`, and the dashboard HTTP server started through the existing `p4_helpers`. Each test isolates with `isolated_db` and the session `HIREEMBER_DIR`. Files are read as bytes or UTF-8 explicitly and compared after whitespace normalisation where docs are involved, so line endings do not matter. API payload checks look at named keys only, never exact key sets.

Legacy resumes (no extraction status) are created by inserting a row directly, which also gives the green-now "no chunks leaves prompts byte-identical" check. Prompt wiring is tested through `gating.process_job` / `score_job_for_ticket` with the shared fake LLM, plus direct hook tests that compare the with-context and default messages.

Every red test fails for a missing behaviour (404 on the new routes, ImportError for new functions or modules, missing table, old strings, missing doc text). `congoforce try-tests` reports PASS.

## Untestable criteria
- The apply-side wiring in `apply.launcher.run_job` and `gen_prompt` is not exercised end to end (it needs a browser launch); only `build_prompt(resume_context=...)` and its exact placement are tested. The verifier should read the launcher code to confirm both pass the ticket resume's `context_block`.
- The phase 6 key and telemetry scans (AC-10) are existing tests and are expected to keep passing.
- "No embedding backend shipped" (AC-5) is not asserted; the verifier should check `pyproject.toml` has no embedding dependency.
- UI behaviour in AC-2 and AC-8 (form clears, list refreshes without reload, disabled button) is a JavaScript runtime effect; tests only check the served page source for the contract strings.

## Open questions
- none
