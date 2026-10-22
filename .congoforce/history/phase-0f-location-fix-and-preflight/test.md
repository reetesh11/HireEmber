# Acceptance test plan — Fix location matching and add a settings check before run and apply

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-2, AC-4, AC-5 (changed) | `tests/acceptance/test_p0f_location_fix.py` | Canada accepts every region (not already-passing Montreal), US accepts states and DC, country-only text for a region target, `Calgary`/`Greater Toronto Area` pass, bare `CA`, multi-part, reject patterns on unrecognised text, updated phase 0e cases | `location_skip_reason` still skips text naming no country or only a region (wrong result) |
| AC-2, AC-3, AC-4, AC-5 (unchanged parts) | `tests/acceptance/test_p0f_location_unchanged.py` | placeholders, empty, no targets, remote handling, Alberta region-only (AC-3, already works), bare CA with Texas, reject patterns, Austin TX / London UK skip reasons | green today (pins behaviour) |
| AC-5 | edited phase 0e tests (`test_p0e_location_rules.py`, `test_p0e_location_gating.py`, `test_p0e_unchanged.py`, `tests/unit/test_location.py`, `tests/unit/test_gating_location.py`) | replace "Berlin, Germany"/"Paris, France"-style skip expectations with "Austin, TX"/"London, UK" | green today; they would otherwise break under R2 |
| AC-10, AC-17, AC-11, AC-8, AC-15, AC-13, AC-14 | `tests/acceptance/test_p0f_preflight_core.py` | `find_needs` per stage and order, dedupe, jobspy only with a board, resume missing cases, malformed models.toml, unreachable tier is a warning, no LLM call, apply needs, report text, `run_preflight` non-interactive/`--no-prompt`, CLI exit 1 and nothing started, `--no-prompt` in help | `hireember.preflight` and `--no-prompt` do not exist yet |
| AC-12 | `tests/acceptance/test_p0f_preflight_unchanged.py` | `run --dry-run`, `apply --mark-applied/--mark-failed/--reset-failed/--dry-run` show no list | green today (no check exists) |
| AC-6, AC-7, AC-9, AC-16, AC-13 | `tests/acceptance/test_p0f_preflight_fix.py` | tier fix saved identically to `save_tier`, custom local (no key asked), same-as-fast copy incl. env key, ordered prompts for three items, resume fix, no re-asking, browser install ok/failed, decline required/optional, Ctrl-C/Ctrl-D, profile/search offers, install-only never prompted, no key in output | `hireember.preflight` does not exist yet |

## Approach
Public surfaces only: `hireember.location.location_skip_reason`, `hireember.preflight` (`find_needs`, `format_report`, `run_preflight`, `is_interactive`, `ask_user`), and the `hireember run` / `hireember apply` CLI via `CliRunner`.
- `p0f_helpers.World` isolates the data folder (profile, resume, searches, models.toml, DB, config dir with empty `sites.yaml`), switches each setting on or off, and makes Claude Code absent through an empty `PATH`, Chrome and Chromium through patched `config.get_chrome_path` / `doctor.chromium_path`, and jobspy absent through `sys.modules["jobspy"] = None`. `models.probe_tier` is replaced by a recorder (reachability only).
- Prompts: `preflight.ask_user` and `preflight.is_interactive` are replaced by a scripted `Ask` that fails the test on any unscripted question. Replies of `KeyboardInterrupt`/`EOFError` model Ctrl-C/Ctrl-D.
- Stages: `hireember.pipeline.run_pipeline` and `hireember.apply.launcher.main/mark_job/reset_failed` are replaced by recorders so tests see whether and with which stages the CLI would start work.
- The browser install test replaces `subprocess.run`; it expects the install to go through it.
- Message fragments are compared after collapsing whitespace, so terminal wrapping does not matter.
- Every new-behaviour test is red today because `hireember.preflight` or `--no-prompt` is missing, or `location_skip_reason` returns the old result. Unchanged-behaviour files pass today.

## Untestable criteria
- AC-1: `pytest` and `ruff check .` are the suite and lint themselves.
- AC-14 (unchanged behaviour of stages, gating, queue, wizard, doctor, models): covered by the existing suite staying green; only the "no LLM call" part has its own test.

## Open questions
- none blocking. Assumptions made from the interface contract: "Skipping <stages>: quality model is not set up." names the stages joined by ", "; `Calgary, Canada` with target Alberta passes; the "Skipping" line for `run score tailor` is `Skipping tailor: ...`.
