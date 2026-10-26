# Parked fixes

Known issues deferred on purpose. Review all of them after the 5 stages are complete.

## From phase 2 (profile, resumes, answers) — PR #5

| # | Severity | Where | Issue |
| --- | --- | --- | --- |
| 1 | major | `answers.py:73-79` | `save_answer(replace=True)` updates only the first row for a key. A conflict caused by two differing bank rows is not cleared by answering the queued item, so the ticket returns to pending and blocks again. |
| 2 | note | `validator.py` | The metric regex ignores currency and bare counts. |
| 3 | note | `validator.py` | `validate_against_profile` always runs now, so a profile without `resume_facts` rejects every employer. |
| 4 | note | `gating.py:131-140` | Path state is duplicated on the jobs row (needed by the apply stage). Revisit when apply is reworked. |
| 5 | note | `pyproject.toml` | Per-file F401 ignore for the frozen phase 2 acceptance tests. Accepted at the time; reconsider. |

## From phase 3 (apply rework) — process notes for the CongoForce repo

These are not HireEmber bugs. They belong in the CongoForce plugin (`/Users/reetesh/workspace/congoforce`).

| # | Where | Issue |
| --- | --- | --- |
| 6 | `congoforce init` | It should create `.claude/settings.json` with `{"worktree": {"bgIsolation": "none"}}` (or set up isolation). Without it, background sessions refuse to write task files in the shared checkout until someone adds the file by hand. |
| 7 | `lib/congoforce/util.py` `md_section` | It ignores code fences. A line starting with `# ` inside a fenced block (for example a comment in a Python snippet) is read as a level-1 heading and ends the section. The generated `interface-contract.md` was cut off after the limits section (99 of 215 lines) and the test author would have worked blind. The fix is to skip lines inside ``` fences. |
| 8 | `congoforce complete` | A placeholder `--summary` is written into `run-log.md` as given, and open questions passed later are not recorded once the stage has moved on. Consider rejecting empty or one-character summaries. |
| 9 | test-author stage | Independence from `tech.md` depends on a separate agent. When the session has no Agent tool, the orchestrator cannot dispatch it. For phase 3 the tests were written by the same session that wrote `tech.md`, from the interface contract only. |

## From phase 3 — HireEmber follow-ups to review after the 5 stages

| # | Severity | Where | Issue |
| --- | --- | --- | --- |
| 10 | note | `apply/gate_server.py` | Hand-rolled stdio MCP server (human decision: start here). Consider moving to the `mcp` SDK later. Only `call_tool` and `TOOLS` are tested, not the transport. |
| 11 | note | `req.md` R10 and AC-8 | They still say 2 minutes between submissions. The human replaced that with a one-day wait for the same company (see `answers.md`). Update the requirement text if it is reused. |
| 12 | note | `tests/acceptance/test_p3_*.py` | Written by the tech-spec author, not an independent agent. The worker-loop duplicate test assumes the loop checks for duplicates before launching Chrome. Revisit if the verifier finds the test unfair. |

## Traceability known exceptions

Requirements with no automated test of their own are listed here and in the Known exceptions
section of `docs/traceability.md`. At the end of phase 6 there are none: every FR, SAF and NFR ID
has a test in the main table.
