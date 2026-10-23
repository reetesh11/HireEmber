# Acceptance test plan - Local web dashboard

## Coverage
| Criterion | File | Test names | Red because |
| --- | --- | --- | --- |
| AC-1 | `tests/acceptance/test_p4_queries.py`, `test_p4_server.py` | links per status, none-case, blocked fallback, `/api/tickets` links, index page | `hireember.web` does not exist |
| AC-2 | same | next_step mapping, blocked_queue, `/api/blocked`, queue answer | `hireember.web.queries` missing |
| AC-3 | `test_p4_data.py`, `test_p4_server.py` | set_note, status/note/referral endpoints, duplicate/override | `tickets.set_note` and the server are missing |
| AC-3 (unchanged) | `test_p4_unchanged.py` | set_status, queue flow, resumes | green today (`expect_red: false`) |
| AC-4 | `test_p4_queries.py`, `test_p4_server.py` | CSV header, rows, quoting, formula guard, HTTP export | `tickets_csv` and `/api/export.csv` missing |
| AC-5 | `test_p4_server.py`, `test_p4_cli.py` | host refusal, Host/Origin 403, CLI exit 2 / port-in-use exit 1 | `create_server`/`HostRefusedError` missing; today's CLI `dashboard` has no `--host` option |
| AC-6 | `test_p4_queries.py`, `test_p4_server.py` | 5,000 tickets under 2 s | modules missing |
| AC-7 | `test_p4_server.py` | updates cursor and changes | server missing |
| AC-8 | `test_p4_data.py` | update/delete/merge answers, resume meta, file replace over HTTP | `update_answer`, `delete_answer`, `merge_answers`, `update_resume_meta` missing |
| AC-9 | `test_p4_queries.py`, `test_p4_server.py` | filters, same set board/list | `TicketFilters` missing |
| AC-10 | `test_p4_cli.py` | help text/options, subprocess start | today's `dashboard` has the old docstring and no options |

## Approach
Tests use only the interface-contract surfaces. Data is seeded through public functions (`store_jobs`, `set_job_score`, `answers.queue_question`, `resumes.add_resume`) plus direct SQL to force status and link columns, via `p4_helpers.py`. The server runs on port 0 in a thread against an `isolated_db` file and is queried with `http.client`. CLI tests use `CliRunner` for refusals and a subprocess for a real start (SIGINT to stop). Red reasons are missing modules (`hireember.web`), missing functions, or the old CLI `dashboard` behaviour.

## Assumptions
- "applied date" is not asserted for applied tickets (the source field is not fixed by the contract); date filters are tested on created dates of non-applied tickets.
- For a blocked ticket with no open queue item, only a non-empty reason and next step are asserted.

## Untestable criteria
- Browser-only behaviour (card moves column, Blocked badge, `Live` indicator, Copy path): the verifier reads the static page; the underlying data and API are tested.
- Doctor output: no hard-coded command list exists to assert.

## Open questions
- none
