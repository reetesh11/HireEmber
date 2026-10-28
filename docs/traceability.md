# Requirements traceability

This table maps every requirement ID in the OpenApply requirements document to the
automated tests that cover it (NFR-10). The Exempt and Known exceptions sections list the
IDs without a test of their own, and why.

Test references are paths under `tests/` or `.github/workflows/`, optionally with `::test_name`.

| Requirement | Description | Tests |
| --- | --- | --- |
| FR-APP-1 | When a ticket starts applying, the system shall open the role's company application page in the dedicated browser profile and record a link to that live browser session on the ticket. | `tests/acceptance/test_p3_ac9_account_resume.py`, `tests/acceptance/test_p3_ac1_gates.py` |
| FR-APP-2 | If the page needs an account or sign-in that is not already active, then the system shall stop, set the ticket to blocked for human with reason account needed, and queue it with the company name and page link. | `tests/acceptance/test_p3_ac1_gates.py`, `tests/acceptance/test_p3_ac9_account_resume.py` |
| FR-APP-3 | When the user has signed in and marks the ticket ready, the system shall resume it from where it stopped. | `tests/acceptance/test_p3_ac9_account_resume.py` |
| FR-APP-4 | When a form field matches an answer in the bank, the system shall fill it, and shall upload the ticket's tailored resume in place of any existing upload. | `tests/acceptance/test_p3_ac2_bank_fill.py`, `tests/acceptance/test_p3_ac11_upload_review.py` |
| FR-APP-5 | If a CAPTCHA, an identity check, or a video or biometric step appears, then the system shall stop, set blocked for human with that reason, and leave the browser on that page. | `tests/acceptance/test_p3_ac1_gates.py` |
| FR-APP-6 | Where review-before-submit is on, the system shall fill the form, stop before the final submit, and queue the ticket for the user. | `tests/acceptance/test_p3_ac11_upload_review.py` |
| FR-APP-7 | When a form is submitted, the system shall look for a confirmation page or email and record it, or else mark the ticket applied but unverified. | `tests/acceptance/test_p3_ac7_confirmation.py` |
| FR-APP-8 | If the page shows the role is closed or the user is not eligible, then the system shall stop and mark the ticket closed with the reason. | `tests/acceptance/test_p3_ac10_closed_manual.py` |
| FR-APP-9 | The system shall log each attempt, including steps taken, answers used and errors, and attach the log to the ticket. | `tests/acceptance/test_p3_ac2_bank_fill.py`, `tests/unit/test_attempts.py`, `tests/acceptance/test_p6_logs.py` |
| FR-CLI-1 | The system shall keep the existing commands for init, run, apply, status, dashboard and doctor, and add commands for schedule, export and answers. | `tests/acceptance/test_p5_unchanged.py`, `tests/unit/test_cli_help.py` |
| FR-CLI-2 | The doctor command checks Python, Chrome, Claude Code, the database and the configured sources, and reports what is missing. | `tests/acceptance/test_ac6_doctor.py::test_doctor_prints_a_status_line_for_each_required_check`, `tests/acceptance/test_ac6_doctor.py::test_chrome_hidden_reports_missing`, `tests/acceptance/test_ac6_doctor.py::test_database_check_missing_then_ok`, `tests/acceptance/test_ac6_doctor.py::test_sources_check_lists_boards_without_linkedin`, `tests/unit/test_doctor.py` |
| FR-DIS-1 | The system shall discover open roles from company career pages and ATS feeds listed in a company list. | `tests/acceptance/test_p5_companies.py` |
| FR-DIS-2 | The system shall not read from, or apply through, LinkedIn. | `tests/acceptance/test_ac3_jobspy_sites.py`, `tests/acceptance/test_ac4_store_skips_linkedin.py`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py`, `tests/unit/test_linkedin_policy.py`, `tests/unit/test_apply_linkedin.py` |
| FR-DIS-3 | When a role is found again, the system shall update its last-seen time and not create a second record. | `tests/acceptance/test_p5_companies.py::test_rediscovery_updates_last_seen_keeps_date_found` |
| FR-DIS-4 | If a source fails, then the system shall log the failure against that source and continue with the others. | `tests/acceptance/test_p5_companies.py::test_failing_source_logged_others_continue` |
| FR-DIS-5 | The user shall be able to maintain the company list with name, careers URL and ATS type. | `tests/acceptance/test_p5_companies.py::test_add_remove_search_list`, `tests/acceptance/test_p5_companies.py::test_next_run_searches_added_and_skips_removed` |
| FR-DUP-1 | Before a ticket moves to started, the system shall look for an existing ticket with the same application URL, or the same company, normalized title and location. | `tests/acceptance/test_p1_ac5_duplicates.py` |
| FR-DUP-2 | If a match is started, applying, blocked or applied, then the system shall set the new ticket to blocked for human with reason duplicate, link it to the existing one and show the reason. | `tests/acceptance/test_p1_ac5_duplicates.py`, `tests/acceptance/test_p3_ac3_duplicate.py` |
| FR-DUP-3 | Where the user wants to apply again, the user shall be able to override the block per ticket with a reason. | `tests/acceptance/test_p1_ac6_override.py` |
| FR-DUP-4 | The system shall enforce limits the user sets on open applications per company and on applications per day. | `tests/acceptance/test_p3_ac8_profile_limits.py`, `tests/unit/test_limits.py` |
| FR-EXP-1 | The user shall be able to download tickets as a CSV file that opens in a spreadsheet, with the current filters applied. | `tests/acceptance/test_p4_queries.py`, `tests/acceptance/test_p5_surfaces.py` |
| FR-EXP-2 | The export shall include company, title, location, status, score, resume used, applied date, links and notes. | `tests/acceptance/test_p4_queries.py` |
| FR-PRO-1 | On first run, the system shall ask the profile questions: name and contact, location, work authorization, availability, compensation expectation, experience level, target roles, skills boundary, resume facts and EEO preferences. | `tests/acceptance/test_p2_ac1_init.py`, `tests/acceptance/test_p0d_profile.py` |
| FR-PRO-2 | The system shall store each answer with the question text, a normalized key, the answer, its source (profile, user or import) and when it was last used. | `tests/acceptance/test_p2_ac4_storage_sensitive.py` |
| FR-PRO-3 | When a form shows a question with no matching answer, the system shall pause the ticket, record the question and queue it for the user. | `tests/acceptance/test_p2_ac2_match.py`, `tests/acceptance/test_p3_ac1_gates.py` |
| FR-PRO-4 | When the user answers a queued question, the system shall add the answer to the bank and let the ticket resume. | `tests/acceptance/test_p2_ac3_queue_answer.py`, `tests/acceptance/test_p3_ac2_bank_fill.py` |
| FR-PRO-5 | If more than one stored answer could match a question and the values differ, then the system shall pause rather than pick one. | `tests/acceptance/test_p2_ac2_match.py`, `tests/acceptance/test_p3_ac1_gates.py` |
| FR-PRO-6 | The system shall not store passwords, tokens or payment details in the profile or the answer bank. | `tests/acceptance/test_p2_ac4_storage_sensitive.py` |
| FR-PRO-7 | The user shall be able to view, edit, merge and delete answers on the dashboard. | `tests/acceptance/test_p4_data.py`, `tests/acceptance/test_p4_server.py` |
| FR-RES-1 | The system shall let the user add several base resumes, each with a name and tags such as a role family. | `tests/acceptance/test_p2_ac5_resumes.py`, `tests/unit/test_resumes.py` |
| FR-RES-2 | When tailoring for a role, the system shall use the base resume the user pinned, or else the best fit to the role. | `tests/acceptance/test_p2_ac5_resumes.py` |
| FR-RES-3 | Each ticket shall keep the exact tailored resume and cover letter it submitted. | `tests/acceptance/test_p2_ac8_pdfs.py` |
| FR-RES-4 | If the user edits a base resume, then tickets already submitted shall keep their original files. | `tests/acceptance/test_p2_ac9_immutable.py` |
| FR-SCH-1 | The system shall run discovery, scoring and tailoring on a schedule the user sets, without the dashboard open. | `tests/acceptance/test_p5_scheduler.py` |
| FR-SCH-2 | When a scheduled run ends, the system shall record a summary: roles found, scored, skipped, tickets created and tickets blocked. | `tests/acceptance/test_p5_runs.py::test_execute_run_writes_one_row_with_counts`, `tests/acceptance/test_p5_surfaces.py::test_api_runs` |
| FR-SCH-3 | If a run is already in progress, then the system shall not start another. | `tests/acceptance/test_p5_runs.py::test_overlapping_runs_produce_one_row` |
| FR-SCH-4 | Where scheduled applying is on, the system shall also apply to eligible tickets, within the per-day limit. | `tests/acceptance/test_p5_scheduler.py` |
| FR-SCH-5 | The user shall be able to run any stage on demand from the command line or the dashboard. | `tests/acceptance/test_p5_runs.py`, `tests/acceptance/test_p5_surfaces.py` |
| FR-SCH-6 | When a run creates tickets that need a human, the system shall add them to the action queue with the company name, reason and page link. | `tests/acceptance/test_p5_runs.py` |
| FR-SCO-1 | When a role is stored, the system shall score it from 1 to 10 against the chosen resume and the profile's target roles, location and level, and store a short reason. | `tests/acceptance/test_p1_ac3_scoring.py`, `tests/acceptance/test_p2_ac7_threshold.py` |
| FR-SCO-2 | Where a role scores below the user's threshold, the system shall mark it skipped and neither tailor nor apply. | `tests/acceptance/test_p2_ac7_threshold.py` |
| FR-TAI-1 | When a role passes the threshold, the system shall produce a tailored resume and cover letter as PDF. | `tests/acceptance/test_p2_ac8_pdfs.py` |
| FR-TAI-2 | The system shall include only employers, projects, schools and metrics listed in the profile's resume facts, and only skills inside the skills boundary. | `tests/acceptance/test_p2_ac6_validator.py`, `tests/unit/test_validator_profile.py` |
| FR-TAI-3 | If tailoring fails validation after the retry limit, then the system shall block the ticket for human review. | `tests/acceptance/test_p2_ac6_validator.py` |
| FR-TRK-1 | The system shall create a ticket for each scored role: pending when the score meets the threshold, skipped when it does not. | `tests/acceptance/test_p1_ac3_scoring.py` |
| FR-TRK-2 | The system shall use the statuses pending, started, applying, blocked for human and applied, plus skipped and closed as end states, and shall record every change with time, actor and reason. | `tests/acceptance/test_p1_ac4_history.py` |
| FR-TRK-3 | Each status shall carry a link where one exists: the job posting for pending, the tailored files for started, the live browser session for applying, the page needing action for blocked, and the confirmation for applied. | `tests/acceptance/test_p4_queries.py` |
| FR-TRK-4 | The dashboard shall show tickets as a board with a column per status and as a sortable list, filterable by company, score, date and resume. | `tests/acceptance/test_p4_queries.py`, `tests/acceptance/test_p4_server.py` |
| FR-TRK-5 | The dashboard shall show a queue of every ticket blocked for human, with its reason and the next step: create an account, sign in, solve a CAPTCHA, answer a question or review. | `tests/acceptance/test_p4_queries.py`, `tests/acceptance/test_p4_server.py` |
| FR-TRK-6 | The user shall be able to change a ticket's status, add notes and add a referral note. | `tests/acceptance/test_p4_server.py`, `tests/unit/test_tickets_notes.py` |
| FR-TRK-7 | When a ticket changes status, the dashboard shall update without a manual refresh. | `tests/acceptance/test_p4_server.py::test_updates_cursor_and_changes` |
| SAF-1 | The system shall never type a password, token, payment detail or government ID into a form. A field of that kind sends the ticket to the human queue. | `tests/acceptance/test_p3_ac1_gates.py` |
| SAF-2 | The system shall not create accounts or sign in. The user does both. | `tests/acceptance/test_p3_ac6_removal.py` |
| SAF-3 | The system shall not bypass CAPTCHAs or bot checks and shall not call a solving service. | `tests/acceptance/test_p3_ac6_removal.py` |
| SAF-4 | The system shall not read from or apply through LinkedIn. | `tests/acceptance/test_ac4_store_skips_linkedin.py::test_linkedin_url_detection_uses_host`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_cli_apply_rejects_linkedin_url`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_launcher_main_rejects_linkedin_url`, `tests/acceptance/test_ac5_apply_rejects_linkedin.py::test_worker_loop_blocks_queued_linkedin_job`, `tests/unit/test_apply_linkedin.py` |
| SAF-5 | Every answer submitted shall trace to the answer bank or the profile. | `tests/acceptance/test_p3_ac2_bank_fill.py` |
| SAF-6 | Tailored documents shall contain no employer, project, school, metric or skill outside the profile. | `tests/acceptance/test_p2_ac6_validator.py` |
| SAF-7 | The apply agent shall run only in a browser profile created for it, never the user's main profile. | `tests/acceptance/test_p3_ac8_profile_limits.py`, `tests/unit/test_chrome_profile.py` |
| SAF-8 | The dashboard shall bind to the local machine only, and data shall leave it only through the LLM provider the user configured and the company sites applied to. | `tests/acceptance/test_p4_server.py`, `tests/acceptance/test_p4_cli.py` |
| SAF-9 | The system shall limit applications per day and per company and wait between submissions. | `tests/acceptance/test_p3_ac8_profile_limits.py` |
| SAF-10 | The apply agent shall load only browser tools and the ticket's files. Mail tools load only if the email-application fallback is enabled. | `tests/acceptance/test_p3_ac6_removal.py` |
| SAF-11 | Text on a job page shall be treated as data. The agent shall not follow instructions found on a page or enter data the form does not ask for. | `tests/acceptance/test_p3_ac5_injection.py` |
| SAF-12 | Sites the user marks as manual-only shall never be automated. | `tests/acceptance/test_p3_ac10_closed_manual.py` |
| NFR-1 | Runs on macOS and Linux with Python 3.11+, Node 18+ and Chrome. | `tests/acceptance/test_ac6_doctor.py::test_python_version_check`, `tests/acceptance/test_ac6_doctor.py::test_node_below_18_or_absent_reports_missing`, `tests/acceptance/test_ac6_doctor.py::test_node_18_or_later_reports_ok`, `tests/acceptance/test_ac2_ci_unchanged.py::test_ci_matrix_covers_python_311_312_313`, `.github/workflows/ci.yml` (Python 3.11 to 3.13 matrix, Linux runner) |
| NFR-2 | Setup from the README to a first scored role shall be possible without editing code. | `tests/acceptance/test_p6_docs.py` |
| NFR-3 | If a run stops after the submit button was pressed, then the system shall not retry that ticket automatically. It shall block the ticket for human with reason outcome unknown. | `tests/acceptance/test_p3_ac4_outcome_unknown.py` |
| NFR-4 | Tickets stuck in applying after an interrupted run shall be recovered on the next start. | `tests/acceptance/test_p3_ac4_outcome_unknown.py` |
| NFR-5 | The system shall copy the database before every migration. | `tests/acceptance/test_p1_ac1_migration.py` |
| NFR-6 | The system shall write a log per run and per ticket, and the dashboard shall link to them. | `tests/acceptance/test_p6_logs.py`, `tests/acceptance/test_p6_dashboard_logs.py` |
| NFR-7 | The system shall send no telemetry. API keys live in an environment file that git ignores, never in the database. | `tests/acceptance/test_p6_keys_telemetry.py` |
| NFR-8 | The system shall record the model and token counts for each stage so the user can see the cost per application. | `tests/acceptance/test_p6_usage.py` |
| NFR-9 | The dashboard list shall load within 2 seconds with 5,000 tickets. | `tests/acceptance/test_p4_queries.py` |
| NFR-10 | Every functional requirement has an automated test; browser steps are tested against local fixture forms. | `tests/acceptance/test_ac7_fixture_form.py::test_fixture_form_is_served_locally_with_required_fields`, `tests/acceptance/test_ac9_traceability.py`, `tests/acceptance/test_p6_traceability.py`, `tests/acceptance/test_ac1_lint.py` |
| NFR-11 | CI runs the tests and lint on every push and pull request. | `tests/acceptance/test_ac2_ci_triggers.py`, `tests/acceptance/test_ac2_ci_unchanged.py::test_ci_failures_are_not_masked`, `.github/workflows/ci.yml` |
| NFR-12 | The README, CONTRIBUTING file and a safety page shall be kept current with the behaviour in sections 4 and 7. | `tests/acceptance/test_p6_docs.py` |

## Exempt

IDs that the requirements document marks as later or out of scope. None.

| Requirement | Reason |
| --- | --- |

## Known exceptions

IDs with no automated test of their own. Each is also listed in `docs/parked-fixes.md`
under "Traceability known exceptions". None.

| Requirement | Reason |
| --- | --- |

## Resume library (phase 7)

These requirement IDs come from the phase 7 task, not the requirements document.

| ID | Description | Tests |
| --- | --- | --- |
| RES-1 | The user can add a resume from a .pdf, .txt or .docx file with a name and optional tags, on the dashboard or the command line. | `tests/acceptance/test_p7_ac1_upload_api.py`, `tests/acceptance/test_p7_ac2_ui_form.py`, `tests/acceptance/test_p7_ac3_docx_cli.py`, `tests/unit/test_web_resume_upload.py` |
| RES-2 | Uploads are checked for format, emptiness, the 10 MB limit, a name and duplicates, and nothing is stored on a refusal. | `tests/acceptance/test_p7_ac1_upload_api.py`, `tests/acceptance/test_p7_ac10_sanitise_logging.py`, `tests/unit/test_resumes_library.py` |
| RES-3 | When a resume is added or its file replaced, the system extracts the text locally and stores sections and bounded chunks. | `tests/acceptance/test_p7_ac4_extraction.py`, `tests/acceptance/test_p7_ac5_store.py`, `tests/unit/test_resume_index.py`, `tests/unit/test_resume_extract.py` |
| RES-4 | The user can search resume chunks by keyword and get ranked results with resume and section. | `tests/acceptance/test_p7_ac6_search.py`, `tests/unit/test_resume_index.py` |
| RES-5 | Scoring, tailoring and form-filling prompts include the best matching chunks, and are unchanged when there are none. | `tests/acceptance/test_p7_ac7_prompts.py`, `tests/acceptance/test_p7_ac11_unchanged.py`, `tests/unit/test_resume_context.py` |
| RES-6 | Each resume shows its extraction status and chunk count, and extraction can be re-run. | `tests/acceptance/test_p7_ac8_status.py`, `tests/unit/test_cli_resume_docx.py` |
| RES-7 | Deleting a resume removes its file, text copy and chunks, and is refused while a ticket uses it. | `tests/acceptance/test_p7_ac9_delete.py`, `tests/unit/test_resumes_library.py` |
