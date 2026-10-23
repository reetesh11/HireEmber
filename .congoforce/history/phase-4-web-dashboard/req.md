---
class: feature
size: large
title: Add local web dashboard with ticket board, blocked queue, answer editing and CSV export
---
# Requirements — Add local web dashboard with ticket board, blocked queue, answer editing and CSV export

## Problem
Users track applications through a Rich terminal view and a static HTML file (`view.py`). They need a local web dashboard over the SQLite ticket data. It should show tickets as a board and a filterable list, surface tickets blocked for human, let them edit tickets, answers and resumes, update live, and export a CSV. Nothing may be reachable from other devices.

## Requirements
- R1. When a ticket is shown, the system shall show the link for its status (pending: job posting; started: tailored files; applying: live browser session; blocked for human: page needing action; applied: confirmation), or state that none exists.
- R2. The system shall show tickets as a board with one column per status in `ALLOWED_STATUSES` and as a sortable list.
- R3. When the user sets filters (company, score, date, resume), the system shall narrow both the board and the list.
- R4. The system shall show a queue of every ticket in "blocked for human" with its reason and next step (create account, sign in, solve CAPTCHA, answer question, review) and a count.
- R5. When the user changes a ticket's status or adds a note or referral note (free text), the system shall write a `ticket_events` row with actor "user".
- R6. When a ticket's status changes in the database, the system shall update open dashboards without a manual refresh.
- R7. The system shall let the user view, edit, merge and delete answers, and edit resumes.
- R8. When the user requests a CSV export, the system shall return one row per ticket in the current filtered view with columns company, title, location, status, score, resume used, applied date, links, notes.
- R9. The server shall bind only to 127.0.0.1.
- R10. If a bind to any other address (for example 0.0.0.0) is requested, then the system shall refuse.
- R11. While the database holds 5,000 tickets, the list endpoint shall respond within 2 seconds.

## Acceptance criteria
- AC-1: A ticket in each of the seven statuses shows its link per R1, or the text that none exists.
- AC-2: With N tickets blocked for human, the queue count is N and each entry shows reason and next step.
- AC-3: Manual status change, note and referral note each write a `ticket_events` row with actor "user"; status change goes through the existing `tickets.set_status` rules.
- AC-4: The CSV for a filtered view has one row per ticket in that view, with every R8 column, and parses in a standard CSV reader (commas, quotes and newlines in notes survive).
- AC-5: Starting the server on 0.0.0.0 is refused with an error; the default and only accepted host is 127.0.0.1.
- AC-6: With 5,000 seeded tickets, the list endpoint responds in under 2 seconds.
- AC-7: A status change written to the database is delivered to an open dashboard through the update endpoint or stream, without reload.
- AC-8: Answers can be viewed, edited, merged and deleted, and resumes edited; each change is visible on reload.
- AC-9: Filters by company, score, date and resume narrow the list and board to the same set of tickets.
- AC-10: A `hireember` CLI command starts the dashboard, and `doctor`/help listings that hard-code command names are updated.

## Out of scope
- Drag-and-drop on the board.
- Authentication, multi-user, remote access.
- Changing the apply runner or scoring logic.
- Replacing the Rich terminal view or `view.py` (unless the tech spec decides otherwise).

## Assumptions
- Framework choice is left to the tech spec; any new dependency goes in `pyproject.toml`.
- "Next step" for a blocked ticket is derived from existing reason or queue data (`answers.list_queue`); no new reasons are invented.
- Merge of answers means combining two answers for equivalent questions into one entry. `answers.py` has no merge or delete today, so these are new.
- Live updates may use polling or server-sent events.
- Tests isolate through `HIREEMBER_DIR`.

## Suggested split
1. Read-only server: localhost-only binding, CLI command, list and board, filters, links, blocked queue, performance (AC-1, 2, 5, 6, 9, 10).
2. CSV export on the filtered view (AC-4).
3. Ticket editing and live updates: status, notes, referral notes, update stream (AC-3, 7).
4. Answers and resumes editing: view, edit, merge, delete (AC-8).

## Open questions
- Where are notes and referral notes stored (the schema has no obvious notes field)? Assume a new column or `ticket_events` entries unless you prefer otherwise.
- Should the work ship as one PR or as the four-part split above?
- Which resumes edits are required: metadata (name, tags) only, or replacing the file as well (`resumes.update_resume`)?
