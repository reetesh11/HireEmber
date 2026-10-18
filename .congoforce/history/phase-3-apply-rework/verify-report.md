# Verify report — phase-3-apply-rework

## Result
PASS — all 11 acceptance criteria are met; three major prompt/launcher issues are worth fixing before or soon after merge.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | password, CAPTCHA, unknown, conflict each block + queue item | met | session.py:answer_field/stop; test_p3_ac1_gates.py |
| AC-2 | answered question fills from bank, log names entry | met | session.py (source `answer:<id>`); answers.py match_answer; test_p3_ac2 |
| AC-3 | duplicate never opens a browser | met | runner.py duplicate check before the agent call; test_p3_ac3 |
| AC-4 | killed after submit -> outcome unknown; stale applying recovered | met | runner.py _settle / recover_stale_tickets; launcher.main calls recovery; test_p3_ac4 |
| AC-5 | injected instruction ignored and logged | met | session.note_page_text; test_p3_ac5. Detection is regex-based, so only a report from the agent via page_text gets logged |
| AC-6 | no CapSolver; no signup/login/Gmail in prompt; no mail tool | met | grep finds CapSolver only in the removal tests; build_mcp_config has playwright + hireember only; agent_tools() |
| AC-7 | applied has link or unverified | met | session.submitted |
| AC-8 | default profile refused; limits hold | met | chrome.assert_dedicated_profile, launcher.main; limits.py computed from DB |
| AC-9 | sign-in blocks `account needed`, queue ready resumes | met | session.stop, answers.ready_queue_item; resume carried by resume_link (see notes) |
| AC-10 | closed role closes for good; manual-only not opened | met | runner.py, session.closed, acquire_job filter |
| AC-11 | tailored resume uploaded; review stops before submit | met | session.resume_path, before_submit incl. skip-once after ready (human answer) |

Untestable part of AC-6 (stdio transport): read gate_server.py. Initialize, tools/list, tools/call, ping and notifications are handled; tool errors return isError; stdin close ends the loop. Looks correct.

## Spec compliance
- Follows the human decisions: one-day same-company wait as a not-before queue (replaces req R10's 2 minutes), queue ready on outcome unknown returns to pending, skip review once after ready, hand-rolled stdio MCP.
- Not asked for but present: a 10-minute retry delay for limit-held tickets (launcher.py _retry_later); uv.lock added (801 lines); history docs under .congoforce/history.

## Code quality
Architecture matches the tech.md diagram. Safety decisions live in Python (GateSession, apply_ticket, limits), which is the right design. Findings:
- major launcher.py:363-365: `bypassPermissions` stays, so `--allowedTools` does not stop built-in tools like Bash. R14 intent not fully met.
- major prompt.py:118-119: not-eligible location still emits `RESULT:FAILED:not_eligible_location`, which nothing reads. A not-eligible role will not be closed (R8).
- major prompt.py:182-184 and the salary section: leftover guess-and-be-strategic guidance conflicts with the gate rules.
- note gate_server.py:107: attempt number inferred as start_attempt()-1.
- note session.py:99: "same application" resume is stored and logged but the prompt never tells the agent to use it.
- note launcher.py:550: hard-coded 10-minute hold retry.

## Recommendation
Ready for a human reviewer. Suggest the implementer fix the three majors (tool restriction, eligibility via `closed`, prompt cleanup) before merge or record them as follow-ups.
