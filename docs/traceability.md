# Requirements traceability

This table maps requirement IDs from the OpenApply requirements document to the
automated tests that cover them. It starts in phase 0 (foundation) and grows
with each phase; NFR-10 requires the table to be completed by phase 6.

Test references are paths under `tests/`, optionally with `::test_name`.

| Requirement | Description | Tests |
| --- | --- | --- |
| FR-DIS-2 | The system shall not read from, or apply through, LinkedIn. | `tests/acceptance/test_ac3_jobspy_sites.py`, `tests/acceptance/test_ac4_store_skips_linkedin.py`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py`, `tests/unit/test_linkedin_policy.py`, `tests/unit/test_apply_linkedin.py` |
| SAF-4 | The system shall not read from or apply through LinkedIn. | `tests/acceptance/test_ac4_store_skips_linkedin.py::test_linkedin_url_detection_uses_host`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_cli_apply_rejects_linkedin_url`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_launcher_main_rejects_linkedin_url`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_worker_loop_blocks_queued_linkedin_job`, `tests/unit/test_apply_linkedin.py` |
| FR-CLI-2 | The doctor command checks Python, Chrome, Claude Code, the database and the configured sources, and reports what is missing. | `tests/acceptance/test_ac6_doctor.py::test_doctor_prints_a_status_line_for_each_required_check`, `tests/acceptance/test_ac6_doctor.py::test_chrome_hidden_reports_missing`, `tests/acceptance/test_ac6_doctor.py::test_database_check_missing_then_ok`, `tests/acceptance/test_ac6_doctor.py::test_sources_check_lists_boards_without_linkedin`, `tests/unit/test_doctor.py` |
| NFR-1 | Runs on macOS and Linux with Python 3.11+, Node 18+ and Chrome. | `tests/acceptance/test_ac6_doctor.py::test_python_version_check`, `tests/acceptance/test_ac6_doctor.py::test_node_below_18_or_absent_reports_missing`, `tests/acceptance/test_ac6_doctor.py::test_node_18_or_later_reports_ok`, `tests/acceptance/test_ac2_ci_unchanged.py::test_ci_matrix_covers_python_311_312_313`, `.github/workflows/ci.yml` (Python 3.11 to 3.13 matrix, Linux runner) |
| NFR-10 | Every functional requirement has an automated test; browser steps are tested against local fixture forms. | `tests/acceptance/test_ac7_fixture_form.py::test_fixture_form_is_served_locally_with_required_fields`, `tests/acceptance/test_ac9_traceability.py`, `tests/acceptance/test_ac1_lint.py` (this table is completed in phase 6) |
| NFR-11 | CI runs the tests and lint on every push and pull request. | `tests/acceptance/test_ac2_ci_triggers.py`, `tests/acceptance/test_ac2_ci_unchanged.py::test_ci_failures_are_not_masked`, `.github/workflows/ci.yml` |
