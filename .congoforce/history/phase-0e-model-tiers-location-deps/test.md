# Acceptance test plan — Add fast/quality model tiers, location pre-skip and one-command install

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-2, AC-4, AC-16, AC-5 (storage) | `tests/acceptance/test_p0e_models_resolve.py` | resolution from env, file, fallback, errors, `save_tier`, `get_client(tier)` | `hireember.models` does not exist; `get_client` takes no tier |
| AC-4, AC-5, AC-6, AC-15 | `tests/acceptance/test_p0e_models_cli.py` | `models show/set/test`, `test_tier`, `probe_tier`, `friendly_error` | no `models` command or module |
| AC-3 | `tests/acceptance/test_p0e_call_sites.py` | one per call site plus a gate flow | call sites call `get_client()` with no tier |
| AC-6, AC-11 | `tests/acceptance/test_p0e_doctor.py` | tier lines, jobspy hint, Chromium check, CLI output | no `check_llm_tiers`, `chromium_path`; stale hint |
| AC-7, AC-8 | `tests/acceptance/test_p0e_location_rules.py` | `location_skip_reason` rules | `hireember.location` missing |
| AC-7, AC-9, AC-12, AC-13 | `tests/acceptance/test_p0e_location_gating.py` | skip per source, prompt, `run_scoring`, status and ticket log | no location check, prompt line, stat or status row |
| AC-8, AC-9 (unchanged) | `tests/acceptance/test_p0e_location_kept.py` | acceptable locations still scored | green now (expect_red false) |
| AC-10, AC-11 | `tests/acceptance/test_p0e_packaging.py` | pyproject, lock, README, doctor source | jobspy is not a dependency; `--no-deps` text exists |
| AC-5 (init), AC-18 | `tests/acceptance/test_p0e_wizard.py` | `run_ai_step`, `offer_chromium_install` | functions missing |
| AC-17 | `tests/acceptance/test_p0e_run_summary.py` | `stage_model_lines`, `run_pipeline` summary | function and summary lines missing |
| AC-14 | `tests/acceptance/test_p0e_unchanged.py` | legacy llm API, no retroactive skip, jobspy OK line | green now (expect_red false) |

## Approach
- Only contract surfaces are used: `hireember.models`, `hireember.llm.get_client`, `hireember.location`, `gating.score_job_for_ticket`, `doctor` checks, `wizard.init`, `pipeline.run_pipeline` and the Typer app through `CliRunner`.
- Isolation: legacy LLM variables are cleared and `hireember.config.MODELS_PATH` is monkeypatched to a temp file (per the contract). The temp data folder from the shared conftest keeps real home folders untouched. Helpers live in `tests/acceptance/p0e_helpers.py`.
- LLM calls are never real. Call sites are checked by replacing the `get_client` name inside each module with a recorder that requires a tier argument. Reachability probes run against a local `http.server` or a closed local port.
- Location skip tests insert jobs with the site and strategy labels of jobspy (`jobspy`), Workday (`workday_api`) and smart extract (`json_ld`) and assert status, reason and zero fake-client calls.
- Existing tests `tests/acceptance/test_ac6_doctor.py` and `tests/unit/test_doctor.py` had their expected check-name list updated to the contract order (`LLM API key` replaced by `Playwright Chromium`, `LLM fast`, `LLM quality`). They are red until the implementation lands.
- Every expected-red test fails today on a missing module, function, command or output, or a wrong result. Green now: `test_p0e_location_kept.py` and `test_p0e_unchanged.py`.

## Untestable criteria
- AC-1: pytest and ruff are the harness; the verifier runs both.
- AC-10 import after clean install: needs a fresh environment and network. Declared dependency and lock file are tested; the verifier may do a clean install.
- AC-14: the existing suite is the check.

## Open questions
- The spec leaves "Vancouver, BC" (province not the user's, no country stated) undefined, so no test covers it.
- The contract gives `Key rejected by <provider>` with provider `custom` for local servers; tests assume that wording.
