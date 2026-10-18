# Verify report — phase-2-profile-resumes-answers

## Result
PASS — all nine criteria met; one major finding (conflict resolution) worth fixing, none blocking.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | Init asks ten groups, stores per group (source profile), explicit skip | met | test_p2_ac1_init (7); run_profile_step wired at wizard/init.py:290 (read, untestable part) |
| AC-2 | match_answer: known / unknown / conflict / identical | met | answers.py match_answer; test_p2_ac2_match |
| AC-3 | Queue answer stores source user, resolves, ticket to pending, usage +1 | met | answers.py answer_queue_item; test_p2_ac3 |
| AC-4 | Five fields, no password key, sensitive never stored | met | answers.py is_sensitive/save_answer; test_p2_ac4 (25) |
| AC-5 | Resumes add/list/pin, resume id set pinned or best fit | met | resumes.py choose_resume; gating.py:60-66; test_p2_ac5 |
| AC-6 | Validator rejects outside-profile facts, retry limit blocks, reason in status | met | validator.py validate_against_profile; gating.py _fail_reason; test_p2_ac6 |
| AC-7 | Threshold skip, exact threshold passes, reasons 1-10 | met | gating.py score_job_for_ticket; test_p2_ac7 |
| AC-8 | Valid PDFs on ticket | met | gating.py tailor_ticket, scoring/pdf.py; test_p2_ac8 |
| AC-9 | Submitted files immutable on resume edit | met | resumes.update_resume never touches tickets; test_p2_ac9 |

## Spec compliance
Architecture matches the tech.md diagram: new profile, answers, resumes, gating modules; scorer and tailor delegate to gating; gating uses tickets, pdf, cover_letter, validator. Gating is wired into the real score and tailor stages (scorer.py:132-158, tailor.py:466-485). Nothing extra built beyond mirroring paths onto the jobs row for the apply stage. Confirmed defaults from gate 2 are followed (replace on re-answer, pending after answer, reuse max_retries=3).

## Code quality
- major: answers.py:73-79 save_answer(replace=True) updates only the first row for a key. A conflict caused by two differing rows is not cleared by answering the queued item; the ticket resumes and blocks again.
- note: validator.py metric regex ignores currency and bare counts; validate_against_profile now always runs, so profiles without resume_facts reject all employers.
- note: gating.py:131-140 duplicates path state on the jobs row (needed by apply stage).
- note: F401 per-file ignore accepted by human.

## Recommendation
Ready for a human reviewer. Consider fixing the conflict-resolution replace behaviour in a follow-up or now.
