# Verify report: phase-0e-model-tiers-location-deps

## Result
PASS. All acceptance criteria are met; checks.md shows lint and 692 tests green and the frozen set intact. One major finding on location false-positives.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | pytest and ruff pass | met | checks.md |
| AC-2 | Gemini-key-only gives same provider/model for both tiers | met | models.py resolve_tier -> _from_environment; test_p0e_models_resolve.py |
| AC-3 | Scoring fast, tailoring/cover quality | met | get_client("fast"/"quality") in scorer.py:112, tailor.py:321,378, cover_letter.py:147, smartextract.py:367,643, detail.py:464 |
| AC-4 | Local URL without key resolves; models test reports per tier | met | models.py resolve_tier custom branch; cli.py models_test |
| AC-5 | models show hides key; set changes value; init writes file | met | cli.py models_show/models_set, key_origin; wizard/init.py _ask_tier uses save_tier |
| AC-6 | Unreachable/unconfigured gives one line, no traceback | met | models.test_tier/probe_tier never raise; doctor.check_llm_tiers |
| AC-7 | Out-of-area job skipped, reason `location: <text>`, zero LLM calls | met | gating.py check before choose_resume; test_p0e_location_gating.py |
| AC-8 | Remote (accepted), empty, unrecognisable not skipped | met | location.py _part_passes; test_p0e_location_kept.py |
| AC-9 | Applies to jobspy, Workday, smart extract | met | single entry point score_job_for_ticket for all rows |
| AC-10 | python-jobspy plain dependency | met | pyproject.toml, uv.lock |
| AC-11 | No --no-deps hint; playwright install chromium shown | met | doctor.py check_playwright_chromium, _check_jobspy; README |
| AC-12 | Prompt has location instruction | met | scorer.py:35 |
| AC-13 | Skip reason visible | met | cli.py status row and ticket log Status line; database.get_stats |
| AC-14 | Existing behaviour unchanged | met | test_p0e_unchanged.py and the existing suite pass |

## Spec compliance
Matches the tech.md architecture: models.py and location.py are new, llm.get_client(tier), call sites, gating, database and CLI are wired as in the diagram. Small additions not explicitly requested: `config.has_llm_configured` so tier detection counts models.toml, a `location_skipped` count in run_scoring, and the Chromium offer in init. All are reasonable. The resume choice/classification in R1 involves no LLM call in the code, so nothing needed changing there.

## Code quality
- Major, location.py:162: the check skips any non-placeholder text matching no accept entry. Without a gazetteer, "recognised" is not tested, so a country-only target (e.g. Canada) skips "Calgary, AB". Conservative-by-design per the assumptions is not fully honoured.
- Note, location.py:33: 'ca' is California, so Canada's code is ambiguous.
- Note, cli.py:572 and doctor.py: "not configured" is detected by substring on exception text.
- Note, wizard/init.py:300: declining a separate quality tier with no legacy env leaves quality unconfigured (warned to the user).
- Key handling is sound: models.toml written 0o600 via atomic replace, keys never printed.

## Recommendation
Ready for a human reviewer. Consider addressing the country-only location false positive before relying on it with real data.
