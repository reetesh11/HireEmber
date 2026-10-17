---
class: feature
size: large
title: Add profile, base resumes, answer bank and score/tailor gating
---
# Requirements — Add profile, base resumes, answer bank and score/tailor gating

## Problem
A user running HireEmber needs the system to know who they are, hold several base resumes, and answer form questions without guessing. Today the wizard (`src/hireember/wizard/init.py`) collects a looser profile, scoring and tailoring (`src/hireember/scoring/`) are not tied to a threshold, base resume or ticket, and unknown form questions are not paused or queued. Phase 2 adds a structured profile, an answer bank with an unknown-question queue, multiple base resumes with pinning, and score-gated, validated tailoring.

## Requirements
Profile and answers
- R1. When init runs on an empty database, the system shall ask each group: name and contact, location, work authorization, availability, compensation expectation, experience level, target roles, skills boundary, resume facts, EEO preferences, and store each answer (FR-PRO-1).
- R2. The system shall store each answer with question text, normalized key, answer, source (profile, user or import) and last-used time (FR-PRO-2).
- R3. When a form question has no matching answer, the system shall set the ticket to blocked for human with reason "unknown question", create a `queue_items` row holding the question text, and type nothing into the field (FR-PRO-3).
- R4. When the user answers a queued question, the system shall add it to the bank with source user, resolve the queue item and let the ticket resume; a later lookup of the same question shall return it and increment times used (FR-PRO-4).
- R5. If more than one stored answer matches a question and the values differ, then the system shall block the ticket with reason "conflicting answers" and queue the question (FR-PRO-5).
- R6. The system shall not store passwords, tokens or payment details in the profile or answer bank. If a question asks for a password, token, payment detail or government ID, then the system shall always queue it and never answer it (FR-PRO-6).

Resumes, scoring, tailoring
- R7. The system shall let the user add several base resumes, each with a name and tags, and list them (FR-RES-1).
- R8. When tailoring, the system shall use the pinned base resume, otherwise the best fit to the role, and record the resume id on the ticket (FR-RES-2).
- R9. The system shall store the paths of the exact tailored resume and cover letter PDFs on the ticket (FR-RES-3, FR-TAI-1).
- R10. If the user edits a base resume, then already submitted tickets shall keep their original files (FR-RES-4).
- R11. When a role is stored, the system shall score it 1 to 10 against the chosen resume and the profile's target roles, location and level, and store a short reason (FR-SCO-1).
- R12. Where a role scores below the threshold (default 7), the system shall mark its ticket skipped and neither tailor nor apply (FR-SCO-2).
- R13. The system shall allow in tailored text only employers, projects, schools and metrics in the profile's resume facts, and only skills inside the skills boundary (FR-TAI-2).
- R14. If tailoring fails validation after the retry limit, then the system shall set the ticket to blocked for human with the validation reason (FR-TAI-3).

## Acceptance criteria
- AC-1: Init on an empty database fed scripted input asks all ten R1 groups and stores an answer for each; a test fails if any group is skipped.
- AC-2: The browser-free answer-matching function returns the bank answer for a known question. For an unknown question it sets the ticket to blocked for human with reason "unknown question" and inserts a `queue_items` row (kind unknown question, question text set). For two matching answers with different values it blocks with reason "conflicting answers" and queues the question. In all blocked cases no answer value is returned.
- AC-3: Answering a queued question stores it with source user, sets the queue item's resolved time, and a later lookup of the same question returns the answer and raises times used by 1 and updates last used.
- AC-4: A stored answer lists all five fields (question text, normalized key, answer, source, last used). `profile.example.json` and the profile schema contain no `password` field. Questions asking for a password, token, payment detail or government ID are queued and never answered, even if a matching bank entry exists.
- AC-5: Two base resumes can be added with names and tags and listed. Tailoring uses the pinned resume when one is pinned, otherwise the best fit, and the ticket's resume id is set in both cases.
- AC-6: The tailoring validator rejects text naming an employer or skill outside the profile. After the retry limit the ticket is blocked for human with the validation reason shown.
- AC-7: A role scoring below the threshold (default 7) has a skipped ticket, no tailored file paths and no application attempt. Every scored role has a score and a reason.
- AC-8: A passing role's ticket holds tailored resume and cover letter PDF paths, and both files exist and open.
- AC-9: After editing a base resume, a submitted ticket's tailored resume and cover letter paths and file contents are unchanged.

## Out of scope
- Filling answers into real browser forms (phase 3).
- Dashboard editing of answers and resumes (phase 4).
- Creating the `tickets`, `ticket_events`, `queue_items`, `answers` and `resumes` tables; phase 1 already added them (`src/hireember/migration.py`).

## Assumptions
- Q7 and Q8 from the input stand: automatic base-resume choice with a pin option, threshold default 7.
- Question matching is on the normalized key; the exact normalization is a design choice.
- The tailoring retry limit uses an existing or configurable value; the default is chosen in design.
- Tests use fake LLM output; no network or browser.
- Phase 1 is merged: ticket statuses, history, threshold setting and duplicate checks live in `src/hireember/tickets.py` and are reused.
- Existing `scorer.py`, `tailor.py`, `validator.py` and `wizard/init.py` are extended rather than replaced.

## Suggested split
1. Profile schema and init questions (R1, R6 schema part, AC-1, AC-4 schema).
2. Answer bank, matching, unknown/conflict queue and answering (R2 to R6, AC-2 to AC-4).
3. Base resumes with pin and best-fit selection (R7, R8, R10, AC-5, AC-9).
4. Scoring threshold, tailoring and validator gating (R9, R11 to R14, AC-6 to AC-8).

## Open questions
- Should the work be run as the four-part split above, or as one large task?
