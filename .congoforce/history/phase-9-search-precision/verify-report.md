# Verify report — phase-9-search-precision

## Result
PASS — all 13 criteria met; only minor notes.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | title_filter whole-word/phrase/case/empty | met | titles.py:41, test_p9_ac1 |
| AC-2 | each path filters before insert, skipped row with reason | met | intake.py:store_filtered, jobspy.py:146, workday.py, companies.py:90 |
| AC-3 | _location_ok removed; one reader for old/new keys | met | grep finds no _location_ok in src; search_config.py:location_lists |
| AC-4 | CA/SF/Calgary word-boundary | met | location.py unchanged matcher, test_p9_ac4 |
| AC-5 | dropped counts, hint, log max 20, Runs tab | met | intake.py DropTally/write_run_log, runs.py, queries.py _dropped_text |
| AC-6 | restore route, UI action, processed afterwards | met | tickets.py:restore_dropped, server.py POST restore, gating.py is_restored exemption |
| AC-7 | init writes include/exclude | met | wizard/init.py, titles.propose_title_lists |
| AC-8 | Profile API read/write canonical keys, no restart | met | search_config.py read/save, exclude_titles popped on save |
| AC-9 | Profile tab, validation, atomic write | met | search_config._validate, save_settings with rollback, index.html |
| AC-10 | scorer role family prompt and cap at 3 | met | scorer.py:113-129 |
| AC-11 | doctor key and empty-lists warnings | met | doctor.py |
| AC-12 | unchanged behaviour | met | existing suite passes (1435) |
| AC-13 | docs | met | README, searches.example.yaml, traceability.md |

## Spec compliance
- Restore returns to `pending` rather than `new`, as approved at gate2.
- `boards` alias for `sites` added, as answered at verify.
- Tickets list hides title/location dropped rows by default and has a status filter; matches the assumptions.
- Architecture: components in tech.md (titles, search_config, intake, restore, profile API) all present and wired as designed.

## Code quality
- scorer.py:128 substring "role family" cap can fire on negated phrasing (note).
- jobspy.py:260 hand-merged tallies and duplicate existence query (note).
- Run-log dropped titles written only on the companies path, which is the real run stage (note).
- Atomic multi-file write with rollback is sound; errors map to 400/422/500.

## Recommendation
Ready for a human reviewer.
