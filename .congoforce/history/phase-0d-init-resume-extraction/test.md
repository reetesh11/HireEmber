# Acceptance test plan — Make hireember init read the resume and pre-fill the profile

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-2 | `tests/acceptance/test_p0d_extract.py`, `test_p0d_step1.py` | pypdf declared, `extract_pdf_text` words, `test_text_pdf_leaves_pdf_and_extracted_text_without_text_prompt` | `hireember.resume_extract` and `run_resume_step` do not exist; pypdf not in dependencies |
| AC-3 | `test_p0d_step1.py` | `test_txt_resume_is_copied_and_nothing_else_is_asked` | `run_resume_step` missing |
| AC-4 | `test_p0d_step1.py`, `test_p0d_extract.py` | `test_pdf_without_usable_text_asks_for_txt_and_finishes` (image-only, blank page, zero bytes, corrupt, short text), `test_txt_prompt_rejects_non_txt_and_missing`, extract returns "" cases | functions missing |
| AC-5 | `test_p0d_step1.py` | registration tests (pdf, txt, twice, `resume list` CLI) | no step function; init never registers |
| AC-6 | `test_p0d_extract.py`, `test_p0d_profile.py` | `test_propose_full_resume`, `test_known_values_are_offered_as_defaults_and_stored_on_enter`, `test_typing_replaces_a_default` | no `propose_profile`; profile step passes no `default=` |
| AC-7 | `test_p0d_profile.py`, `test_p0d_profile_stable.py`, extract tests | partial resume, ambiguous values, blank re-ask | proposals missing (missing-field half is green today and pinned) |
| AC-8 | `test_p0d_profile.py`, `test_p0d_profile_stable.py` | keep flow, decline keep, partly stored group | partly-stored test is red (email default absent); the rest are green today and pin behaviour |
| AC-9 | `test_p0d_profile.py` | `test_doctor_shows_resume_ok_after_pdf_flow` | no step 1 function to produce `resume.txt` from the PDF |
| AC-10 | `test_p0d_step1.py` | declined (n, Enter, N, other), accepted (y, YES), PDF declined, no prompt when none exists | overwrite prompt missing |
| AC-11 | `test_p0d_step1.py` | `test_confirmation_output_shows_lines_count_and_path`, character count, decline loop | confirmation missing |
| AC-12 | `test_p0d_unchanged.py` | plain questions, non-resume questions never get defaults, doctor states | green today and after |
| AC-1 | none | see untestable | |

## Approach
Tests call only the public surfaces in the interface contract: `hireember.resume_extract`, `run_resume_step`, `run_profile_step` with a scripted `ask(question, **kwargs)`, the `resume list` and `doctor` CLI commands, `resumes.list_resumes`, `answers.list_answers`. The data folder is isolated by monkeypatching `config.APP_DIR`, `RESUME_PATH`, `RESUME_PDF_PATH` and `PROFILE_PATH` (and any same-named copies in the wizard module). PDFs are generated from raw bytes in `p0d_helpers.py` (no extra dependency). Encrypted PDFs are not generated (no library to build one here); they fall under the same "text-less" code path as the corrupt and empty cases that are tested. Red tests fail today with ImportError/missing attribute (new module/function) or a wrong result, not setup errors.

## Untestable criteria
- AC-1: meta; `pytest` and `ruff check .` are enforced by the whole suite and the existing lint acceptance test.

## Open questions
- none

## Criterion mapping note
tests.json now has a separate entry for each of AC-3, AC-4, AC-5, AC-7, AC-9, AC-10 and AC-11, pointing at the files and tests named in the coverage table above.
