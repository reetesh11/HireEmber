# Acceptance test plan — Harden doctor source checks and phase 0b follow-ups

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-2 | `tests/acceptance/test_phase0c_doctor_followups.py` | `test_ac2_bad_searches_sites_reports_missing[int/string/mapping]`, `test_ac2_non_string_items_report_missing` | `check_sources` raises or splits the string today |
| AC-3 | same | `test_ac3_employers_not_mapping`, `test_ac3_sites_yaml_not_list[int/string]` | no type validation today |
| AC-4 | same | `test_ac4_resolve_jobspy_sites_rejects_non_list[str/int/dict]`, `test_ac4_search_jobs_reports_error`, `test_ac4_full_crawl_reports_error`, `test_ac4_run_discovery_does_not_raise` | no ValueError raised today |
| AC-5 | same | `test_ac5_stray_hireember_file_ignored`, `test_ac5_legacy_notice_printed_with_stray_file` | a `.hireember` file is chosen today |
| AC-6 | same | `test_ac6_readme_badge_points_at_hireember`, `test_ac6_contributing_commands_exist` | docs still say applypilot / `hireember discover` |
| AC-7 | same | `test_ac7_resolve_jobspy_sites_none_and_list`, `test_ac7_valid_configs_unchanged`, `test_ac7_resolve_app_dir_unchanged` | green now (unchanged behaviour) |

## Approach
Public surfaces only: `check_sources`, `resolve_jobspy_sites`, `resolve_app_dir`, discovery functions, the Typer `app` help, and the doc files. Config paths are monkeypatched as in existing doctor tests; the DB uses `isolated_db`. AC-5 notice is checked in a subprocess with a fake HOME.

## Untestable criteria
- AC-1: it is the full pytest and ruff run; the verifier runs it.

## Open questions
- none
