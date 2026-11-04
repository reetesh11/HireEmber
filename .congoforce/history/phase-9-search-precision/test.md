# Acceptance test plan — Filter discovery by target title and location, editable in the dashboard

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p9_ac1_titles.py` | whole word, phrase, case, empty lists, include/exclude order, `propose_title_lists` (AC-7 title half) | `hireember.titles` does not exist |
| AC-2 | `tests/acceptance/test_p9_ac2_paths.py` | jobspy DataFrame, workday and careers-page via company list, `store_filtered` | `hireember.intake` missing, `store_jobspy_results` takes no filter |
| AC-3 | `tests/acceptance/test_p9_ac3_ac4_location.py` | `_location_ok` removed, `location_lists` precedence | `_location_ok` still in discovery; `search_config` missing |
| AC-4 | `tests/acceptance/test_p9_ac4_location_unchanged.py` | old/new key parity, CA/SF word boundaries, Calgary | green now: `location.py` already matches whole words; pins it (expect_red false) |
| AC-5 | `tests/acceptance/test_p9_ac5_report.py` | `DropTally`, run log max 20, discover `dropped`/`hint`, Runs tab column | `intake` missing, no `dropped` key, no `Dropped` column |
| AC-6 | `tests/acceptance/test_p9_ac6_restore.py` | `restore_dropped`, HTTP route 200/404/409, list hiding and `status=` filter, restored job scored, `title_skipped` | restore API, constants and route missing |
| AC-7 | `tests/acceptance/test_p9_ac7_init.py` | proposed lists written, existing lists kept, init message | `_setup_searches` writes no title lists |
| AC-8 | `tests/acceptance/test_p9_ac8_settings.py` | read/save, alias removal, remote flag, next-call visibility, validation messages, atomic rollback, API 200/400/422/500 | `search_config` and `/api/profile` missing |
| AC-9 | `tests/acceptance/test_p9_ac9_ui.py` | Profile tab, texts, ids, Restore button, status filter in served page | page has no Profile tab |
| AC-10 | `tests/acceptance/test_p9_ac10_scorer.py` | role family line and rule, cap at 3 | scorer does not read `title_include` |
| AC-10 | `tests/acceptance/test_p9_ac10_unchanged.py` | empty include: no line, no cap | green now (expect_red false) |
| AC-11 | `tests/acceptance/test_p9_ac11_doctor.py` | misspelt key, no-suggestion key, empty lists, clean config, missing file | `check_search_config_keys` missing |
| AC-12 | `tests/acceptance/test_p9_ac12_unchanged.py` | remote/empty/placeholder locations, foreign location skip, `store_jobs`, no-config discovery keeps all | green now (expect_red false) |
| AC-13 | `tests/acceptance/test_p9_ac13_docs.py` | example yaml keys within `KNOWN_KEYS`, README terms, traceability terms | `search_config` missing; docs not updated |

## Approach
Tests use only the public surfaces in the interface contract. Config isolation: `config.SEARCH_CONFIG_PATH` and `PROFILE_PATH` are monkeypatched to temp files (helper `p9_helpers.use_config`, which also patches the names bound in `wizard.init` and `doctor`). Discovery paths use fake company adapters and a pandas DataFrame; the scorer uses a stub `get_client`; the HTTP tests start the real server on an ephemeral port. Atomicity is tested by making `os.replace` fail for `profile.json`.

AC-4 turned out to hold already (the current `location.py` matches whole words), so those tests are green and pinned as unchanged-behaviour; the criterion's remaining risk (a second matcher in `discovery/`) is covered by the AC-3 file.

## Untestable criteria
- None. UI behaviour (AC-9) is checked on the served page source (texts, ids, endpoints), like earlier phases; interactive behaviour (Enter adds, Save disabled until change) is left to the verifier reading code.

## Open questions
- none
