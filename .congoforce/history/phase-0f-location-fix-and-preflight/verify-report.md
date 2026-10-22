# Verify report: phase-0f-location-fix-and-preflight

Result: PASS. All criteria are met and there are no blocking findings.

## Pass 1: spec compliance
- AC-1: met. checks.md shows lint and 802 tests passing.
- AC-2 to AC-5: met. `_part_passes` in location.py maps regions to countries. A country target accepts all its regions, and a region target accepts only that region. Text with no recognised token passes. Bare `CA` passes if either meaning fits. The `location: <text>` reason is unchanged. The phase 0e tests that conflicted with R2 were updated.
- AC-6, AC-7: met. `run_preflight` prints one list of all missing items, then prompts for each fixable one in turn. After each fix it re-evaluates, and the run continues without a restart. Tier answers are saved through `models.save_tier`.
- AC-8: met. Without a terminal, or with `--no-prompt`, it prints the list and returns `proceed=False`. cli.py exits with code 1 before any stage starts.
- AC-9: met. `_decide` stops when no stage can run. Otherwise it drops the affected stages and their downstream stages, and prints "Skipping ...".
- AC-10: met. `find_needs` asks for a tier only for the stages that use it: score the fast tier, tailor and cover the quality tier, and discover neither.
- AC-11: met. Claude Code CLI and Chrome are non-fixable needs: the list shows their install pointers and the user is not prompted.
- AC-12: met. `--dry-run` skips the check in `run` and `apply`. The `apply` utility modes return before the check is reached.
- AC-13: met. Answers are never echoed. Prompts go through `ask_user`, and the API key is only passed on as `password=True` input.
- AC-14: met. The check reuses the `doctor` helpers, `models.resolve_tier` and `models.probe_tier`. The probe sends no LLM call, and `doctor` and `models` are unchanged.

Decisions recorded in answers.md are followed:
- "Use the same settings as the fast tier" copies the values into models.toml.
- An environment-only tier counts as missing once models.toml configures any tier.
- `apply` runs the check after `check_worker_profiles`.

## Pass 2: quality
The code is clear and small. It reuses the wizard steps. `_setup_searches` gained optional `ask` and `out` parameters, and the old call path still works. The architecture matches tech.md: cli calls preflight, preflight uses doctor, models, resumes and config, runs the wizard steps in its prompt loop, and returns stages and skip notes to cli and `run_pipeline`. No component was added or dropped. The only extra is the `skipped_notes` parameter on `run_pipeline`, which reprints the skip notes after the summary table.

Findings are all notes, listed in verify-review.json: dead `_LLM_STAGES`, the private `_UPSTREAM` import, lenient bare-`CA` handling, and the conditional kwargs in cli.py.
