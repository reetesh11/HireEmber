# Acceptance test plan — Add jobs by URL and apply to them

## Coverage
| Criterion | File | Red because |
| --- | --- | --- |
| AC-1 | `test_p10_ac1_layouts.py` | `hireember.addjob` and `hireember.enrichment.page` do not exist |
| AC-2, AC-15, AC-16 | `test_p10_ac2_dedupe.py` | `hireember.addjob` does not exist |
| AC-3 | `test_p10_ac3_manual.py` | `addjob` missing; `score_job_for_ticket` still skips/changes a manual job |
| AC-3 (unchanged) | `test_p10_ac3_unchanged.py` | green now: other jobs are still location-skipped |
| AC-4, AC-5, AC-10 (CLI) | `test_p10_ac4_cli.py` | no `add-job` command |
| AC-4, AC-5, AC-11 (run level) | `test_p10_ac11_apply.py` | `addjob.run_add_jobs` missing |
| AC-6 | `test_p10_ac6_refusal.py` | `hireember.urlfetch` missing |
| AC-7 | `test_p10_ac7_failures.py` | `urlfetch`/`addjob` missing |
| AC-8 | `test_p10_ac8_text.py`, `test_p10_ac8_cli_text.py` | `addjob` missing; no `--text` option |
| AC-9 | `test_p10_ac9_api.py` | route `/api/jobs/add` (404), no `results` in status, no `runs.start_task_async` |
| AC-10 | `test_p10_ac10_rows.py` | `run_add_jobs`, `format_summary`, state helpers missing |
| AC-12 | `test_p10_ac12_ui.py` | panel text absent from `index.html` |
| AC-12 (unchanged) | `test_p10_ac12_unchanged.py` | green now: no review-off control |
| AC-13 | `test_p10_ac13_logs.py` | `addjob` missing |
| AC-14 | `test_p10_ac14_docs.py` | README section, reference, traceability and help text missing |

## Approach
Tests use public surfaces only: `addjob`, `urlfetch`, `enrichment.page`, `runs.start_task_async`, the
`hireember` Typer app through `CliRunner`, and the dashboard server over HTTP. Network is never used:
`fetch`/`extract` are injected, or `fetch_page` runs on `httpx.MockTransport` with a fake resolver.
Gating, preflight and `apply.launcher.main` are stubbed with the module attributes named in the contract
(`Pipeline` helper in `p10_helpers.py`), which also records call order. The phase 9 filters are patched to raise.
`tests/acceptance/conftest.py` is new and only provides the shared `conn` fixture.
Every red test currently fails with a missing module, command, route, option or text, not a setup error.
Fixture pages for the ATS layouts use realistic markup; where the contract does not say where location comes
from (Greenhouse, Lever, Ashby, Workday), the fixtures put it in an element whose class or data attribute contains
"location".

## Untestable criteria
- AC-12 keyboard operation, screen-reader labelling and live disabling of buttons: needs a browser. Tests check labels, texts and `role` attributes in the served page; the verifier reads the markup and script.

## Open questions
- none
