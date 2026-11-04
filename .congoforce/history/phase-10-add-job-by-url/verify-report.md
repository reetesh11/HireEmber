# Verify report — phase-10-add-job-by-url

## Result
PASS — every criterion is met and there are no blocking or major findings. checks.md shows lint, 1628 tests and the frozen set all passing.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | add_job_from_url and the layout cascade | met | addjob.py:168; enrichment/page.py; test_p10_ac1_layouts |
| AC-2 | Tracking parameters removed, duplicates by url and application_url | met | addjob.py:35-46, 78-87; test_p10_ac2_dedupe |
| AC-3 | strategy manual, phase 9 filters bypassed | met | addjob.py:147-152; gating.py:74-108; test_p10_ac3_* |
| AC-4 | No launcher without --apply, launcher only for added URLs | met | addjob.py:317-334; cli.py:545 |
| AC-5 | Preflight first, review always explicit | met | addjob.py:321, 334; the server passes review=True and has no review field |
| AC-6 | Scheme and private-address refusal before any body is read | met | urlfetch.py:52-81, 100-111; redirects are checked per hop and the body is streamed only after the check |
| AC-7 | 404 and login give distinct reasons and blocked tickets | met | addjob.py:90-99, 137-143; urlfetch.py:84-89 |
| AC-8 | Text for a blocked URL continues the pipeline | met | addjob.py:119-130; cli.py --text; server /api/tickets/{id}/description |
| AC-9 | POST /api/jobs/add with caps, lock and status route | met | server.py:167-190, 513-540; runs.start_task_async; the 409 comes from the lock |
| AC-10 | Result rows and CLI table | met | addjob.py:236-249; cli.py:549-560 |
| AC-11 | CAPTCHA ends blocked for human, daily limit | met | addjob.py:218-230, 328-330 |
| AC-12 | Dashboard box, buttons, progress and table | met | index.html. Buttons are real button elements, labels are tied to inputs, status and alert roles are set, and the buttons are disabled while a run is active |
| AC-13 | No keys or resume text in logs | met | addjob.py logs only the exception type at error level; test_p10_ac13_logs |
| AC-14 | README, CLI help and traceability | met | README.md, docs/traceability.md, cli.py help and docstring |
| AC-15 / AC-16 | Applied-ticket duplicate, same URL twice | met | addjob.py:119-126; tests |

## Spec compliance
- The change matches the tech.md architecture diagram. The add-job code never calls the intake filters.
- The location bypass applies to all manual jobs in gating.py. The human accepted this at gate 2.
- The CLI does not de-duplicate repeated URLs. This follows the human's final answer and AC-16.

## Code quality
- No blocking or major findings. The notes are in verify-review.json. The main one is the DNS re-resolution gap in urlfetch.py:74-77.
- Errors are handled per URL (addjob.py:179, 256) and the run lock is always released.
- The apply loop uses the existing launcher, scheduler limit and preflight, so nothing was duplicated.
- The only changes to existing tests were the CLI command list test and the phase 6 key scan allowlist. The human approved the allowlist edit.

## Recommendation
Ready for a human reviewer.
