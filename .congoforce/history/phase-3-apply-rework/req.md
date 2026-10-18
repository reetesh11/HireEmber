---
class: feature
size: large
title: Rework the apply stage with human gates and safety rules
---
# Requirements — Rework the apply stage with human gates and safety rules

## Problem
Today the apply stage runs Claude Code over Chrome with permissions bypassed. It signs in and signs up with the password from `profile.json`, reads verification codes through a Gmail MCP, solves CAPTCHAs with CapSolver and guesses screening answers. The user wants the agent to do only the safe parts: fill from the answer bank and the profile, upload the ticket's tailored resume, and hand every account, CAPTCHA, unknown question or sensitive field to a human through the queue. Code touched: `src/hireember/apply/launcher.py`, `prompt.py`, `chrome.py`, `src/hireember/doctor.py`, `src/hireember/wizard/init.py`, plus the ticket and queue modules from phases 1 and 2.

## Requirements
- R1. When a ticket starts applying, the system shall open the role's application page in the dedicated browser profile and record the Chrome debugging address on the ticket as the live-session link (FR-APP-1).
- R2. If the page needs an account or a sign-in that is not active, then the system shall stop, block the ticket for human with reason account needed, and queue it with the company name and page link. No credential is typed and no signup is attempted (FR-APP-2, SAF-2).
- R3. When the user marks a blocked ticket ready, the system shall resume it on the same application without restarting it (FR-APP-3).
- R4. When a form field matches an answer in the bank or a profile value, the system shall fill it and shall upload the ticket's tailored resume in place of any existing upload (FR-APP-4).
- R5. If a CAPTCHA, an identity check, or a video or biometric step appears, then the system shall stop, block the ticket for human with that reason, and leave the browser on that page. It shall not try to solve it (FR-APP-5, SAF-3).
- R6. Where review-before-submit is on, the system shall fill the form, stop before the final submit and queue the ticket for the user. The setting is off by default (FR-APP-6).
- R7. When a form is submitted, the system shall record a confirmation link, or else mark the ticket applied but unverified (FR-APP-7).
- R8. If the page shows the role is closed or the user is not eligible, then the system shall close the ticket with the reason and shall not retry it (FR-APP-8).
- R9. The system shall write an attempt log per ticket with steps, answers used with their source, and errors, and shall show it when the ticket is opened (FR-APP-9, SAF-5).
- R10. The system shall enforce at most 3 open applications per company, 25 per day and 2 minutes between submissions, including across a batch run. A ticket held back by a limit stays pending with a visible reason (FR-DUP-4, SAF-9).
- R11. If a field asks for a password, token, payment detail or government ID, then the system shall leave it empty and block the ticket for human (SAF-1).
- R12. If a form question has no answer in the bank, or two bank answers conflict, then the system shall block the ticket for human and queue a question or conflict item. Once answered, the next form with that question shall be filled from the bank.
- R13. The system shall run the apply agent only in a browser profile created for it, and startup shall refuse the default Chrome profile (SAF-7).
- R14. The system shall load only browser tools and the ticket's files into the agent. No mail tool is loaded, and the email-application fallback is removed (SAF-10).
- R15. The system shall treat page text as data. An instruction found on a page shall not change what is filled, and the attempt shall be logged (SAF-11).
- R16. Where a company is flagged manual-only, the system shall send its tickets straight to blocked for human with reason manual site and shall never automate them (SAF-12). The user sets the flag per company.
- R17. If a run stops after the submit button was pressed, then the system shall block the ticket with reason outcome unknown and shall not retry it automatically (NFR-3).
- R18. When the system starts, it shall recover tickets left in applying: move each to blocked or pending with a reason (NFR-4).
- R19. The system shall not send a duplicate ticket to a browser.
- R20. The repository shall contain no CapSolver code, key, dependency or doctor check, and the apply code shall have no signup, login or Gmail routine (SAF-2, SAF-3).

## Acceptance criteria
All run against local fixture forms, with no live site.
- AC-1: A password field, a CAPTCHA, an unknown question and two conflicting answers each end with the ticket blocked for human, the field left empty, and a `queue_items` row of the matching kind.
- AC-2: After a queued question is answered, the next fixture form with the same question is filled from the bank and the attempt log names the bank entry as the source.
- AC-3: A duplicate ticket never opens a browser.
- AC-4: A fixture run killed after submit leaves the ticket blocked with reason outcome unknown, not pending. A stale applying ticket is recovered on next start with a reason.
- AC-5: A page with an injected instruction does not change what is filled, and the attempt is logged.
- AC-6: The repository has no CapSolver code, key, dependency or doctor check. The apply prompt has no signup, login or Gmail fallback, and a default run's tool list has no mail tool.
- AC-7: Every applied ticket has a confirmation link or the unverified flag.
- AC-8: Startup refuses the default Chrome profile. Limits of 3 open per company, 25 per day and 2 minutes between submissions hold across a batch.
- AC-9: A sign-in page blocks the ticket with reason account needed, no credential typed, and a queue entry holding the company name and page link. After the user marks it ready, the run resumes on the same application.
- AC-10: A closed-role page closes the ticket with its reason and the ticket is not retried. A ticket for a company flagged manual-only goes to blocked for human with reason manual site without opening a browser.
- AC-11: The uploaded file name on a fixture form matches the ticket's tailored resume. With review-before-submit on, no submit happens and the ticket is queued.

## Out of scope
- Real job sites. Tests use local fixture forms only.
- The web dashboard (phase 4), scheduler and company watch (phase 5), release hardening (phase 6).
- Fixes parked in `docs/parked-fixes.md`.
- An email-application fallback. It is removed, not reworked.

## Assumptions
- Phases 1 and 2 are on `main` (PR #5 merged): tickets, `queue_items`, answer bank, profile and resume choice are available.
- Decisions from the requirements doc hold: review-before-submit off by default (Q2), email fallback removed (Q3), limits 3 / 25 / 2 minutes (Q5), live-session link is the Chrome debugging address (Q6).
- The limits are settings with those defaults, not hard-coded.
- "Ready" is an existing ticket action from phase 1's queue handling; no new status is needed.
- The manual-only flag is per company (human decision). Whether it is a column or a setting keyed by company is left to the tech spec; a way to set it from the CLI is in scope.
- Run as one large task, not split (human decision).

## Suggested split
Not used; the human chose one large task. For reference only:
1. Safety removal (R13, R14, R20).
2. Blocking gates (R2, R3, R5, R8, R11, R12, R15, R16).
3. Fill and submit (R4, R6, R7, R9, R17, R18, R19).
4. Limits and live link (R1, R10).

## Open questions
- none
