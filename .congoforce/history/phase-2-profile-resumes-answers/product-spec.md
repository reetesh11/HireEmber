# Product spec — Add profile, base resumes, answer bank and score/tailor gating

## User-facing behaviour

HireEmber is a CLI (`hireember`, Typer: `init`, `run`, `apply`, `status`, `dashboard`, `doctor`). Phase 2 has no browser and no dashboard UI. Everything is reached through `hireember init`, new CLI commands and the existing ticket status output. Command names below are proposals for tech-spec to confirm. The behaviour is what matters.

### 1. Profile (init)
- `hireember init` on an empty database walks through ten groups, in this order, as headed steps:
  1. Name and contact
  2. Location
  3. Work authorization
  4. Availability
  5. Compensation expectation
  6. Experience level
  7. Target roles
  8. Skills boundary (the only skills tailored text may claim)
  9. Resume facts (employers, projects, schools, metrics)
  10. EEO preferences
- Every group is asked. A blank answer is not silently dropped. For optional items (for example EEO) the user must type an explicit "decline" or "skip". The skip is stored as such, so a stored answer exists for every group.
- Each answer is stored in the answer bank (see 2) with source `profile`.
- The wizard never asks for a password, token or payment detail. `profile.example.json` and the profile schema have no `password` field. Today's `profile.example.json` has `personal.password`, which is removed.
- Re-running init on a non-empty database does not re-ask groups that are already stored. It offers to keep or change each group.

### 2. Answer bank
- Each stored answer has: question text, normalized key, answer, source (`profile`, `user` or `import`), last-used time. Times used is also kept.
- `hireember answers list` prints a table with columns: Question, Key, Answer, Source, Last used (and Used count). Empty state: `No answers stored yet. Run "hireember init" or answer queued questions.`
- Matching (browser-free function): given a question text and ticket, it returns one of three outcomes.
  - Answered: the stored answer. Times used goes up by 1 and last-used is updated.
  - Unknown: no answer is returned. The ticket becomes `blocked for human` with reason `unknown question`. A `queue_items` row is created with kind `unknown question`, the ticket id and the question text. Nothing is typed into the field.
  - Conflict: two or more stored answers match and their values differ. No answer is returned. The ticket becomes `blocked for human` with reason `conflicting answers`. The question is queued (kind `conflicting answers`).
- Sensitive questions: if the question asks for a password, token, payment detail (card, bank account, CVV) or government ID (SSN, SIN, passport, national ID), it is always queued and never answered, even if a bank entry matches. Reason on the ticket: `sensitive question`. Queue kind: `sensitive question`.
- Answering a queued question: `hireember queue list` shows open items (id, ticket, kind, question). `hireember queue answer <id> "<answer>"` stores the answer with source `user`, sets the item's resolved time, and returns the ticket from `blocked for human` to `pending`, so it can resume. Output: `Answer saved. Ticket <n> is ready to resume.`
- Answering a sensitive-kind item resolves it but does not store the answer. Output: `Not saved: passwords, tokens, payment details and government IDs are never stored. Ticket <n> stays blocked for human.`
- A later lookup of the same question returns the answer, times used +1, last-used updated, with no pause.

### 3. Base resumes
- `hireember resume add <file> --name "<name>" --tags "<t1,t2>"` adds a base resume. `hireember resume list` shows Id, Name, Tags, Pinned, File, Added.
- `hireember resume pin <id>` pins one resume. At most one is pinned, and pinning another replaces it. `hireember resume unpin` clears it.
- Empty state for list: `No base resumes. Add one with "hireember resume add".`
- Editing a base resume (replacing its file or text) affects only future tailoring.

### 4. Scoring, tailoring, gating
- When a role is stored it is scored 1 to 10 against the chosen base resume plus the profile's target roles, location and level. The score and a short reason (one or two sentences) are saved on the ticket.
- Chosen resume: the pinned one, otherwise the best fit by role and resume tags. The resume id is saved on the ticket in both cases. If no base resumes exist, scoring and tailoring do not run for that ticket. It becomes `blocked for human` with reason `no base resume`.
- Threshold: the existing setting, default 7. Score below threshold: ticket becomes `skipped` with reason `score <n> below threshold <t>`. No tailoring and no application attempt. Score equal to or above the threshold proceeds.
- Tailoring writes a tailored resume PDF and a cover letter PDF. Their paths are saved on the ticket. Both files exist and open as valid PDFs.
- Validation: tailored text may name only employers, projects, schools and metrics from the profile's resume facts, and only skills within the skills boundary. A violation triggers a retry. After the retry limit the ticket becomes `blocked for human` with the validation reason, for example `validation failed: employer "Acme Corp" not in resume facts`. `hireember status` and the ticket history show that reason.
- Submitted tickets keep their original tailored files. Later base resume edits never rewrite or relink them.

## Acceptance criteria

- AC-1: Init on an empty database with scripted input asks all ten groups listed above and stores at least one answer per group (source `profile`). A test fails if any group is not asked, or has no stored answer. An explicit "skip" counts as an answer, a silent blank does not.
- AC-2: The matching function, without a browser, behaves as follows.
  - Known question: returns the bank answer.
  - Unknown question: returns no value, sets the ticket to `blocked for human` with reason `unknown question`, and inserts a `queue_items` row with kind `unknown question` and question text set.
  - Two matching answers with different values: returns no value, blocks with reason `conflicting answers`, and queues the question. Two matches with identical values are treated as a single match and answered.
  - In every blocked case no answer value is returned and nothing is written to a field.
- AC-3: Answering a queued question stores it with source `user` and sets the queue item's resolved time. The ticket leaves `blocked for human` (to `pending`). A later lookup of the same question returns the answer, raises times used by exactly 1 and updates last used.
- AC-4: A stored answer lists all five fields: question text, normalized key, answer, source, last used. `profile.example.json` and the profile schema contain no `password` key anywhere. Questions asking for a password, token, payment detail or government ID are queued (kind and reason `sensitive question`) and never answered, even when a matching bank entry exists. No such value is accepted into the bank via `queue answer` or `init`.
- AC-5: Two base resumes can be added with names and tags and listed with both. Tailoring uses the pinned resume if one is pinned. Otherwise it uses the best fit. The ticket's resume id is set in both cases and equals the id shown in `resume list`.
- AC-6: The validator rejects tailored text naming an employer or skill outside the profile (resume facts and skills boundary). After the retry limit the ticket is `blocked for human` and the validation reason is visible in `status` and in the ticket history.
- AC-7: A role scoring below the threshold (default 7) has a `skipped` ticket, null tailored resume and cover letter paths, and no application attempt. Every scored role has a score from 1 to 10 and a non-empty reason. A role scoring exactly the threshold is not skipped.
- AC-8: A passing role's ticket holds tailored resume and cover letter PDF paths. Both files exist, are non-empty and open as PDFs.
- AC-9: After editing a base resume, a submitted ticket's tailored resume and cover letter paths are unchanged and the file contents are byte-identical.

## Edge cases and errors
- Question matching ignores case, punctuation and extra whitespace (for example "Are you authorized to work in the US?" matches "are you authorized to work in the us"). Exact normalization is a tech-spec decision.
- Same question queued twice for the same ticket: one open queue item only, not duplicates.
- Answering an already-resolved or unknown queue id: `Queue item <id> not found or already resolved.` Exit code non-zero. No change.
- Empty answer given to `queue answer`: rejected with `Answer cannot be empty.` Item stays open.
- `resume add` with missing file: `File not found: <path>.` Unsupported type: `Unsupported format. Provide a .txt or .pdf file.` Duplicate resume name: rejected with `A resume named "<name>" already exists.`
- `resume pin` with an unknown id: `No resume with id <id>.`
- Scoring or tailoring with a failing LLM call: the ticket is `blocked for human` with the error reason. It is never silently skipped or applied.
- Ticket history gets an event for every status change, with the reason (existing phase 1 behaviour).
- Re-answering a question already in the bank with a different value (source `user`) is out of the matching path. It updates or adds an entry. See open questions.

## Out of scope
- Filling answers into real browser forms (phase 3).
- Dashboard editing of answers and resumes (phase 4).
- Creating the `tickets`, `ticket_events`, `queue_items`, `answers` and `resumes` tables (phase 1).
- Storing or autofilling credentials, tokens, payment data or government IDs, ever.

## Open questions
- Should `init` import the existing `~/.hireember/profile.json` and resume.txt as source `import` answers and a first base resume, or start fresh?
- When the user answers a question that already has a different bank answer, should it replace the old one, or be added as a second entry (which would then cause a "conflicting answers" block)? Proposal: replace.
- After a queued answer, should the ticket go back to `pending`, or back to its prior status? Proposal: `pending`.
- For a blank EEO answer, is "decline to answer" stored as the answer value? Proposal: yes.
- The retry limit default for tailoring (design may reuse the existing `max_retries`).
