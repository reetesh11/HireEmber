# OpenApply — Requirements Document

Oct 14, 2026 · @Reetesh

## 1. Overview

OpenApply is a local-first, open-source tool that finds roles matching your resume on company career sites, tailors the resume per role, fills and submits the application, and tracks every application on a local board, pausing only where a human must act.

**Problem.** Applying to senior roles one form at a time is slow and repetitive. Existing open-source tools either automate LinkedIn directly, which puts the account at risk, improvise answers to screening questions, or handle passwords and CAPTCHAs on their own.

**Goals**

- G1. Discover roles on company career sites and ATS feeds on a schedule, and score them against the resume.
- G2. Tailor the resume and cover letter per role without inventing facts.
- G3. Fill and submit applications on company sites in a browser session the user can watch.
- G4. Answer screening questions only from a user-approved answer bank, and add every new question to that bank.
- G5. Track every application as a ticket with a status, a history and links, and block duplicate applications.
- G6. Stop and queue anything that needs a human: account creation, login, CAPTCHA and unknown questions.

**Non-goals**

- Applying through LinkedIn, or scraping it.
- Creating accounts, entering passwords or solving CAPTCHAs automatically.
- Multi-user hosting, cloud sync or a paid service.
- Automated lookups of your LinkedIn network. A manual referral note on a ticket is enough.

**Success measures**

| Measure | Target |
| --- | --- |
| Duplicate submissions to the same company, title and location | 0 |
| Submitted answers not traceable to the answer bank or profile | 0 |
| Submitted applications with a status record and history | 100% |
| Submissions with a recorded confirmation, or marked unverified | 100% |

## 2. Users, scope and decisions

The user is one job seeker applying to professional roles, running everything on their own computer with their own browser profile and API access. Nothing is hosted.

**Decisions already made**

| Area | Decision | Reason |
| --- | --- | --- |
| Application channel | Company career sites and ATS forms only | LinkedIn prohibits automated access and can restrict the account |
| Codebase | Fork of ApplyPilot (AGPL-3.0) | Discovery, scoring and tailoring already exist |
| Data store | Local SQLite is the source of truth, with a sheet export | Local-first, no external service |
| Accounts and login | The human creates accounts and signs in, once per company, in a dedicated browser profile | The tool never handles passwords |
| CAPTCHAs | Pause the job and hand it to the human | Not bypassed |
| Screening answers | Taken only from the answer bank; an unknown question blocks the job | No guessed answers |
| Interface | Local web dashboard | Chosen by the user |
| Licence | AGPL-3.0, inherited from the fork | Required by the upstream licence |
| Development | Built with the congoforce plugin from this document | Chosen by the user |

**In scope**

- Profile and answer bank, with several resumes.
- Scheduled discovery, scoring and per-role tailoring.
- Browser-based filling and submission on company sites.
- A ticket tracker with statuses, links and duplicate blocking.
- A local web dashboard and CSV export.

**Out of scope**

- Anything that applies through, or reads from, LinkedIn.
- Bypassing CAPTCHAs, identity checks or login walls.
- A mobile app, a hosted service or multiple users.

**Terms**

- **Ticket:** one application to one role, with a status and a history.
- **Answer bank:** the saved answers to form questions, each with its source.
- **Human gate:** a point where the tool stops and queues the ticket for the user.

## 3. Baseline: ApplyPilot as inherited

ApplyPilot (Python, about 9,600 lines, AGPL-3.0, last commit 8 March 2026) supplies discovery, scoring and tailoring that OpenApply keeps, and an apply stage that OpenApply reworks. This comes from reading the code, not from running it.

**What is kept or extended**

| Component | What exists today | Plan |
| --- | --- | --- |
| Discovery | JobSpy job-board search, a Workday scraper driven by `employers.yaml`, a generic career-site extractor | Keep; remove LinkedIn as a source |
| Scoring | LLM fit score from 1 to 10 against the resume and preferences | Keep |
| Tailoring | Per-job resume and cover letter as PDF, checked against `skills_boundary` and `resume_facts` so it cannot invent skills or employers | Keep; support several base resumes |
| Storage | One SQLite `jobs` table keyed by URL, with `apply_status`, attempt count and timestamps | Extend with new tables |
| Apply | Spawns Claude Code with the Playwright MCP over Chrome, permissions bypassed | Rework (see below) |
| Dashboard | Live terminal view built with Rich | Replace with a web dashboard |
| Run mode | A `--continuous` polling loop | Add a real schedule |

**What is removed or replaced**

| Existing behaviour | Replacement |
| --- | --- |
| Automatic login, then signup, using the password in `profile.json`, with verification codes read through a Gmail MCP | Human gate: the ticket is queued and the user signs in |
| CAPTCHA solving through CapSolver | Ticket moves to blocked for human |
| Plaintext `password` field in the profile | Field removed; no credentials stored |
| Prompt rule to answer yes to tools in the same domain and not undersell the candidate | Answers come only from the answer bank |
| Hardcoded location eligibility and salary-negotiation rules written for a US candidate | Settings read from the user's profile |

Two items need checking before design is final: whether LinkedIn can be switched off through configuration alone, and whether the email-application fallback in the apply prompt stays (see section 11).

## 4. Functional requirements

Requirements use EARS phrasing ("When X, the system shall Y") and carry IDs, with an acceptance criterion in the same row so each can become a numbered acceptance test.

### 4.1 Profile and answer bank

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-PRO-1 | On first run, the system shall ask the profile questions: name and contact, location, work authorization, availability, compensation expectation, experience level, target roles, skills boundary, resume facts and EEO preferences. | Running init on an empty database asks every listed group and stores each answer; none is skipped silently. |
| FR-PRO-2 | The system shall store each answer with the question text, a normalized key, the answer, its source (profile, user or import) and when it was last used. | A stored answer can be listed with all five fields. |
| FR-PRO-3 | When a form shows a question with no matching answer, the system shall pause the ticket, record the question and queue it for the user. | The ticket becomes blocked for human with reason unknown question, the question appears in the dashboard queue, and nothing is typed into that field. |
| FR-PRO-4 | When the user answers a queued question, the system shall add the answer to the bank and let the ticket resume. | After answering, a later form with the same question is filled without pausing. |
| FR-PRO-5 | If more than one stored answer could match a question and the values differ, then the system shall pause rather than pick one. | A test with two conflicting matches ends in a queued question, not a filled field. |
| FR-PRO-6 | The system shall not store passwords, tokens or payment details in the profile or the answer bank. | The profile schema has no password field, and a form question asking for a password is queued, not answered. |
| FR-PRO-7 | The user shall be able to view, edit, merge and delete answers on the dashboard. | Each of the four actions changes the bank and is visible on reload. |

### 4.2 Resumes

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-RES-1 | The system shall let the user add several base resumes, each with a name and tags such as a role family. | Two resumes can be added and listed with their names and tags. |
| FR-RES-2 | When tailoring for a role, the system shall use the base resume the user pinned, or else the best fit to the role. | Each ticket records which base resume it used. |
| FR-RES-3 | Each ticket shall keep the exact tailored resume and cover letter it submitted. | The file paths are on the ticket and both files open. |
| FR-RES-4 | If the user edits a base resume, then tickets already submitted shall keep their original files. | Editing a base resume leaves submitted tickets unchanged. |

### 4.3 Discovery

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-DIS-1 | The system shall discover open roles from company career pages and ATS feeds listed in a company list. | For a list of three companies, roles are stored with company, title, location, source, URL and date found. |
| FR-DIS-2 | The system shall not read from, or apply through, LinkedIn. | No LinkedIn source is enabled by default, and a test confirms LinkedIn URLs are rejected by discovery and by the apply stage. |
| FR-DIS-3 | When a role is found again, the system shall update its last-seen time and not create a second record. | Running discovery twice leaves one record per role. |
| FR-DIS-4 | If a source fails, then the system shall log the failure against that source and continue with the others. | One failing source does not stop a run, and the failure shows in the run log. |
| FR-DIS-5 | The user shall be able to maintain the company list with name, careers URL and ATS type. | Adding and removing a company changes what the next run searches. |

### 4.4 Scoring and tailoring

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-SCO-1 | When a role is stored, the system shall score it from 1 to 10 against the chosen resume and the profile's target roles, location and level, and store a short reason. | Every scored role has a score and a reason. |
| FR-SCO-2 | Where a role scores below the user's threshold, the system shall mark it skipped and neither tailor nor apply. | A role below the threshold has no tailored files and no application attempt. |
| FR-TAI-1 | When a role passes the threshold, the system shall produce a tailored resume and cover letter as PDF. | Both files exist for the ticket. |
| FR-TAI-2 | The system shall include only employers, projects, schools and metrics listed in the profile's resume facts, and only skills inside the skills boundary. | A validator test fails when tailored text names a company or skill outside the profile. |
| FR-TAI-3 | If tailoring fails validation after the retry limit, then the system shall block the ticket for human review. | The ticket shows blocked for human with the validation reason. |

### 4.5 Application

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-APP-1 | When a ticket starts applying, the system shall open the role's company application page in the dedicated browser profile and record a link to that live browser session on the ticket. | While the run is active, the ticket shows a link that leads to the session. |
| FR-APP-2 | If the page needs an account or sign-in that is not already active, then the system shall stop, set the ticket to blocked for human with reason account needed, and queue it with the company name and page link. | No credentials are typed and no signup is attempted; the queue entry shows the page to open. |
| FR-APP-3 | When the user has signed in and marks the ticket ready, the system shall resume it from where it stopped. | The resumed run continues on the same application without restarting it. |
| FR-APP-4 | When a form field matches an answer in the bank, the system shall fill it, and shall upload the ticket's tailored resume in place of any existing upload. | The uploaded file name matches the ticket's tailored resume. |
| FR-APP-5 | If a CAPTCHA, an identity check, or a video or biometric step appears, then the system shall stop, set blocked for human with that reason, and leave the browser on that page. | No solving is attempted and the queue entry names the reason. |
| FR-APP-6 | Where review-before-submit is on, the system shall fill the form, stop before the final submit, and queue the ticket for the user. | With the setting on, no application is submitted without a user action. |
| FR-APP-7 | When a form is submitted, the system shall look for a confirmation page or email and record it, or else mark the ticket applied but unverified. | Every applied ticket has a confirmation link or the unverified flag. |
| FR-APP-8 | If the page shows the role is closed or the user is not eligible, then the system shall stop and mark the ticket closed with the reason. | The ticket is closed with a reason and is not retried. |
| FR-APP-9 | The system shall log each attempt, including steps taken, answers used and errors, and attach the log to the ticket. | Opening a ticket shows its attempt log. |

### 4.6 Duplicate control

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-DUP-1 | Before a ticket moves to started, the system shall look for an existing ticket with the same application URL, or the same company, normalized title and location. | A second posting of the same role is detected before any browser work begins. |
| FR-DUP-2 | If a match is started, applying, blocked or applied, then the system shall set the new ticket to blocked for human with reason duplicate, link it to the existing one and show the reason. | The new ticket shows a link to the earlier one and does not run. |
| FR-DUP-3 | Where the user wants to apply again, the user shall be able to override the block per ticket with a reason. | The override and its reason appear in the ticket history. |
| FR-DUP-4 | The system shall enforce limits the user sets on open applications per company and on applications per day. | Reaching a limit leaves further tickets pending with a visible reason. |

### 4.7 Tracker and dashboard

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-TRK-1 | The system shall create a ticket for each scored role: pending when the score meets the threshold, skipped when it does not. | Each scored role has exactly one ticket, pending or skipped. |
| FR-TRK-2 | The system shall use the statuses pending, started, applying, blocked for human and applied, plus skipped and closed as end states, and shall record every change with time, actor and reason. | The history of any ticket lists each change in order. |
| FR-TRK-3 | Each status shall carry a link where one exists: the job posting for pending, the tailored files for started, the live browser session for applying, the page needing action for blocked, and the confirmation for applied. | A ticket in each status shows its link, or states that none exists. |
| FR-TRK-4 | The dashboard shall show tickets as a board with a column per status and as a sortable list, filterable by company, score, date and resume. | Dragging is not required; filters narrow both views. |
| FR-TRK-5 | The dashboard shall show a queue of every ticket blocked for human, with its reason and the next step: create an account, sign in, solve a CAPTCHA, answer a question or review. | The queue count equals the number of blocked tickets. |
| FR-TRK-6 | The user shall be able to change a ticket's status, add notes and add a referral note. | Each manual change is recorded in the history with the user as actor. |
| FR-TRK-7 | When a ticket changes status, the dashboard shall update without a manual refresh. | A status change made by a running job appears on an open dashboard. |

### 4.8 Scheduler and human-gate queue

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-SCH-1 | The system shall run discovery, scoring and tailoring on a schedule the user sets, without the dashboard open. | On a running machine, a scheduled run starts at the set time and logs its result. |
| FR-SCH-2 | When a scheduled run ends, the system shall record a summary: roles found, scored, skipped, tickets created and tickets blocked. | The summary is visible on the dashboard for each run. |
| FR-SCH-3 | If a run is already in progress, then the system shall not start another. | Two overlapping triggers produce one run. |
| FR-SCH-4 | Where scheduled applying is on, the system shall also apply to eligible tickets, within the per-day limit. | With the setting off, a scheduled run never opens a browser to apply. |
| FR-SCH-5 | The user shall be able to run any stage on demand from the command line or the dashboard. | Each stage can be started on its own and reports its result. |
| FR-SCH-6 | When a run creates tickets that need a human, the system shall add them to the action queue with the company name, reason and page link. | After a run, the queue lists every new blocked ticket. |

### 4.9 Export and command line

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR-EXP-1 | The user shall be able to download tickets as a CSV file that opens in a spreadsheet, with the current filters applied. | The file has one row per ticket and matches what the dashboard shows. |
| FR-EXP-2 | The export shall include company, title, location, status, score, resume used, applied date, links and notes. | Each listed column is present. |
| FR-CLI-1 | The system shall keep the existing commands for init, run, apply, status, dashboard and doctor, and add commands for schedule, export and answers. | Each command prints help and runs on a fresh install. |
| FR-CLI-2 | The doctor command shall check Python, Chrome, Claude Code, the database and the configured sources, and report what is missing. | Running doctor on a machine without Chrome reports Chrome as missing. |

## 5. Data model

SQLite stays the single source of truth. The existing `jobs` table is kept and new tables are added beside it, created idempotently the way the current code does with `CREATE TABLE IF NOT EXISTS` and `ensure_columns`.

**Tables**

| Table | Purpose | Key fields |
| --- | --- | --- |
| `jobs` (existing) | One row per discovered role, keyed by URL | Existing columns, plus company id, normalized title, normalized location, last seen |
| `companies` | The company list that discovery searches | name, careers URL, ATS type, active |
| `tickets` | One application to one role | job URL, status, status reason, resume id, tailored resume path, cover letter path, score, score reason, duplicate-of, unverified flag, referral note, notes, created, updated |
| `ticket_events` | Full status history | ticket id, status, actor (system or user), reason, link, link kind, time |
| `queue_items` | Every human gate | ticket id, kind (account needed, sign in, CAPTCHA, identity check, unknown question, review), reason, page link, question text, resolved time |
| `answers` | The answer bank | question text, normalized key, answer, source, times used, last used |
| `resumes` | Base resumes | name, tags, file path, pinned, added |
| `runs` | Scheduled and manual runs | kind, start, end, summary |
| `settings` | User settings | key, value (thresholds, limits, schedule, review-before-submit) |

**Duplicate key.** A ticket's key is the lowercased company, normalized title and normalized location, checked alongside the application URL.

**Migrating an existing ApplyPilot database.** On startup the system adds the new tables, keeps every `jobs` row, and creates a ticket for each row that has been tailored or attempted, mapping the old `apply_status` as follows:

| Old value | New status | Reason recorded |
| --- | --- | --- |
| empty, tailored | pending |  |
| in\_progress | pending | stale lock from an interrupted run |
| applied | applied | unverified |
| failed | blocked for human | the stored error text |
| manual | blocked for human | manual ATS |
| captcha | blocked for human | CAPTCHA |
| login\_issue | blocked for human | account needed |
| expired | closed | role expired |

Migration acceptance: running it twice changes nothing the second time, and the row count of `jobs` is the same before and after.

## 6. Application status lifecycle

A ticket moves through five statuses and ends as applied, skipped or closed; only blocked for human waits on the user.

&#91;embedded content: ticket status lifecycle · 5 statuses, 2 end states\]

A scored role starts pending, or skipped if it is below the threshold. The second line in each box is the link the ticket carries (FR-TRK-3). Skipped and closed are end states, drawn dashed.

| Status | Meaning | Moves on when |
| --- | --- | --- |
| Pending | Scored above the threshold and waiting its turn | A run or the user picks it up and the duplicate check passes |
| Started | Tailored resume and cover letter being made or ready | The files exist and the daily and per-company limits allow an attempt |
| Applying | Browser session open and the form being filled | A confirmation is found, or something needs the user |
| Blocked for human | Stopped, with a reason and the page that needs action | The user acts, or marks it closed |
| Applied | Submitted, with a confirmation link or the unverified flag | End state for the application |
| Skipped | Below the score threshold, or skipped by the user | End state |
| Closed | The role is closed or the user is not eligible | End state |

Reasons a ticket can be blocked: account needed, sign-in needed, CAPTCHA, identity check, unknown question, conflicting answers, review before submit, duplicate, tailoring failed, manual-only site and outcome unknown. A ticket blocked as outcome unknown is never retried automatically (NFR-3). Every change is recorded with time, actor and reason (FR-TRK-2), and the user can move a ticket by hand (FR-TRK-6).

## 7. Safety, compliance and guardrails

The tool acts only inside limits that protect the user's accounts, data and reputation, and each limit below must be testable.

| ID | Rule | Acceptance criterion |
| --- | --- | --- |
| SAF-1 | The system shall never type a password, token, payment detail or government ID into a form. A field of that kind sends the ticket to the human queue. | A test form with a password field ends as blocked for human with the field empty. |
| SAF-2 | The system shall not create accounts or sign in. The user does both. | The apply code has no signup or login routine. |
| SAF-3 | The system shall not bypass CAPTCHAs or bot checks and shall not call a solving service. | The repository has no solver integration, key or dependency. |
| SAF-4 | The system shall not read from or apply through LinkedIn. | LinkedIn URLs are rejected by discovery and by the apply stage. |
| SAF-5 | Every answer submitted shall trace to the answer bank or the profile. | The attempt log lists each field with the source of its value. |
| SAF-6 | Tailored documents shall contain no employer, project, school, metric or skill outside the profile. | The validator test in FR-TAI-2 passes on every tailored file. |
| SAF-7 | The apply agent shall run only in a browser profile created for it, never the user's main profile. | Startup refuses to use the default Chrome profile. |
| SAF-8 | The dashboard shall bind to the local machine only, and data shall leave it only through the LLM provider the user configured and the company sites applied to. | The dashboard is unreachable from another device on the network. |
| SAF-9 | The system shall limit applications per day and per company and wait between submissions. | Limits from FR-DUP-4 hold across a batch run. |
| SAF-10 | The apply agent shall load only browser tools and the ticket's files. Mail tools load only if the email-application fallback is enabled. | The agent's tool list in a default run contains no mail tool. |
| SAF-11 | Text on a job page shall be treated as data. The agent shall not follow instructions found on a page or enter data the form does not ask for. | A test page containing an injected instruction does not change behaviour, and the attempt is logged. |
| SAF-12 | Sites the user marks as manual-only shall never be automated. | A ticket for a manual-only site goes straight to blocked for human with reason manual site. |

**Compliance.** The project stays under AGPL-3.0. Upstream copyright notices and attribution to ApplyPilot are kept, new files carry the licence header, and the README states that the project is a fork. Company sites and ATS vendors may restrict automation in their terms, and the user is responsible for following them.

## 8. Non-functional requirements

The fork has no tests yet: its CI file runs `pytest tests/`, but the `tests/` folder does not exist, and CI is manual-trigger only. Building a test harness is therefore the first piece of work (section 10).

| ID | Requirement | Measure |
| --- | --- | --- |
| NFR-1 | The system shall run on macOS and Linux with Python 3.11 or later, Node 18 or later for the browser MCP, and Chrome. Windows is not a target for the first release. | `doctor` passes on a clean macOS and a clean Linux install. |
| NFR-2 | Setup from the README to a first scored role shall be possible without editing code. | A new user completes it using only the README and the init questions. |
| NFR-3 | If a run stops after the submit button was pressed, then the system shall not retry that ticket automatically. It shall block the ticket for human with reason outcome unknown. | A test that kills the run after submit leaves the ticket blocked, never pending. |
| NFR-4 | Tickets stuck in applying after an interrupted run shall be recovered on the next start. | A stale applying ticket is moved to blocked or pending with a reason. |
| NFR-5 | The system shall copy the database before every migration. | A backup file exists after a migration run. |
| NFR-6 | The system shall write a log per run and per ticket, and the dashboard shall link to them. | Each ticket page opens its attempt log. |
| NFR-7 | The system shall send no telemetry. API keys live in an environment file that git ignores, never in the database. | A search of the repository and database finds no key. |
| NFR-8 | The system shall record the model and token counts for each stage so the user can see the cost per application. | Each ticket shows model and token totals. |
| NFR-9 | The dashboard list shall load within 2 seconds with 5,000 tickets. | A seeded database meets the limit on a laptop. |
| NFR-10 | Every functional requirement shall have at least one automated test. Browser steps shall be tested against local fixture forms, not live company sites. | `pytest tests/` and `ruff check src/` pass, and a traceability table maps each requirement ID to a test. |
| NFR-11 | CI shall run the tests and lint on every push and pull request. | A failing test turns the CI check red. |
| NFR-12 | The README, CONTRIBUTING file and a safety page shall be kept current with the behaviour in sections 4 and 7. | Each is updated in the pull request that changes the behaviour. |

## 9. Architecture and integrations

The stages do not hand work to each other directly: each reads the tickets it needs from the local database and writes its result back.

&#91;embedded content: components and what they read and write · 3 stages, 3 outside services\]

The database is the source of truth. The CLI and scheduler start stages and record runs. The apply stage drives a dedicated Chrome profile that the user signs in to, and the dashboard reads and writes the same database.

| Integration | How it is used | Notes |
| --- | --- | --- |
| Claude Code CLI | The apply stage runs it once per ticket with the Playwright MCP | Needs the user's own access; `doctor` checks and pins a tested version |
| Playwright MCP and Chrome | Drives the dedicated Chrome profile over a local debugging port | The port address is the ticket's live-session link (Q6) |
| LLM provider | Scoring, tailoring and cover letters, through the provider the user configures | Keys live in the environment file, never in the database |
| Dashboard server | A small local web server over SQLite, bound to the local machine | Framework chosen in the P4 technical spec |
| Scheduler | The operating system's scheduler or a built-in loop | Chosen in the P5 technical spec |
| Gmail MCP | Not loaded by default (SAF-10) | Loaded only if Q3 keeps email applications |

**Technology constraints.** Python 3.11 or later, SQLite, the existing `src/applypilot` package layout until the rename in Q9 is decided, and no new service that must run outside the user's machine.

## 10. Phased delivery plan

Delivery is seven phases, each sized as one congoforce task that ends in one pull request. Copy each phase's rows into its own file, for example `docs/requirements/phase-1-data-layer.md`, and start it with `/congoforce:run docs/requirements/phase-1-data-layer.md`. The "Done when" column becomes that phase's acceptance criteria.

| Phase | Scope | Depends on | Done when |
| --- | --- | --- | --- |
| P0 Foundation | Test harness with pytest, a local fixture form for browser tests, CI on every push, lint, fork notice in the README, LinkedIn excluded from discovery and apply (FR-DIS-2, SAF-4), `doctor` checks (FR-CLI-2), NFR-1, NFR-10, NFR-11 | None | `pytest tests/` and `ruff check src/` pass in CI on push, and a test confirms LinkedIn URLs are rejected |
| P1 Data layer | New tables and the ApplyPilot migration with a backup (section 5, NFR-5), tickets and status history (FR-TRK-1, FR-TRK-2), duplicate detection and override (FR-DUP-1 to FR-DUP-3) | P0 | Migrating a sample ApplyPilot database twice gives the same result with the same `jobs` row count, and duplicate tickets are blocked and linked |
| P2 Profile, resumes and answer bank | Init questionnaire, answer storage, matching and conflict pause, queue for unknown questions (FR-PRO-1 to FR-PRO-6), several base resumes and selection (FR-RES-1 to FR-RES-4), tailoring validation and failure block (FR-TAI-1 to FR-TAI-3, FR-SCO-1, FR-SCO-2) | P1 | Init stores every answer group, an unknown question creates a queue item without a browser, and a tailored file naming an employer outside the profile fails validation |
| P3 Apply stage rework | Session link, account-needed gate, CAPTCHA and identity-check gate, answer-bank filling, resume upload, review mode, confirmation capture, closed roles, attempt log, limits (FR-APP-1 to FR-APP-9, FR-DUP-4), removal of auto login, signup and CAPTCHA solving, and SAF-1 to SAF-3, SAF-5, SAF-7, SAF-9 to SAF-12, NFR-3, NFR-4 | P1, P2 | Against fixture forms: a password field, a CAPTCHA and an unknown question each end blocked for human with the field empty; a duplicate does not run; a run killed after submit ends blocked with outcome unknown; an injected page instruction is ignored and logged |
| P4 Web dashboard | Board and list, links per status, action queue, manual changes and notes, live updates, answer-bank and resume editing, CSV export (FR-TRK-3 to FR-TRK-7, FR-PRO-7, FR-EXP-1, FR-EXP-2), local-only binding (SAF-8), NFR-9 | P1, P3 | Every status shows its link or states none exists, the queue count matches blocked tickets, the export matches the filtered view, and 5,000 seeded tickets list within 2 seconds |
| P5 Scheduler and company list | Scheduled discovery, scoring and tailoring, run summaries, no overlapping runs, optional scheduled applying, on-demand stages, queue after each run, company list maintenance (FR-SCH-1 to FR-SCH-6, FR-DIS-1, FR-DIS-3 to FR-DIS-5, FR-CLI-1) | P1, P2 | A scheduled run on a test clock logs a summary, overlapping triggers start one run, and with scheduled applying off no browser opens |
| P6 Release hardening | Per-run and per-ticket logs, model and token records, README, CONTRIBUTING and safety page, requirement-to-test traceability table (NFR-2, NFR-6, NFR-8, NFR-12) | P0 to P5 | A new user reaches a first scored role from the README alone, and every requirement ID maps to a passing test |

Order: P0, P1, P2, P3, P4, P5, P6. P4 and P5 do not depend on each other and can swap. Questions Q1 to Q11 in section 11 should be answered before P3 starts, since Q2, Q3 and Q6 change the apply stage.

## 11. Open questions, risks and assumptions

Eleven decisions are still open, and each has a proposed default so development is not blocked.

**Open questions**

- [x] Q1. Are skipped and closed acceptable as end states beside the five statuses you named? Proposed: yes.
- [x] Q2. Should review-before-submit be off by default, matching fully automatic submission, or on until the attempt logs look clean? Proposed: off.
- [x] Q3. The inherited apply prompt can send an application by email through the Gmail MCP when a role asks for that. Keep it with a confirmation step, or remove it? Proposed: remove for the first release.
- [x] Q4. Can LinkedIn be switched off in discovery by configuration alone, or does the JobSpy integration need a code change? To be checked in phase 0.
- [x] Q5. Default limits. Proposed: 3 open applications per company, 25 per day, and a 2-minute gap between submissions.
- [x] Q6. What should the live-browser link point to: the local Chrome debugging address, which works only while a run is live on the same machine, or screenshots streamed into the dashboard? Proposed: the debugging address first.
- [x] Q7. Should the base resume be chosen automatically, or should the tool ask when two fit equally? Proposed: automatic, with a pin option.
- [x] Q8. Default score threshold. The inherited default is 7. Proposed: keep 7.
- [x] Q9. The project's name and public repository location. `openapply` is a placeholder.
- [x] Q10. Should the shipped Workday employer list stay in the repository, or become a user-supplied file? Proposed: ship a small example only.
- [x] Q11. Are referral notes enough, or should a later release add a structured field for who you know at a company? Proposed: notes only.

**Risks**

| Risk | Mitigation |
| --- | --- |
| Upstream has had no commits since March 2026, so its ATS handling may already be stale | Fixture-based tests, and start with a few ATS types rather than all |
| The browser agent misreads a field and submits a wrong answer | Answer-bank-only rule, attempt log with a source per field, optional review mode |
| ATS vendors detect automation and block submissions even without a CAPTCHA | Dedicated profile, limits and pauses between submissions, manual-only list |
| LLM cost per application grows unnoticed | Score threshold and per-ticket token records |
| The apply stage depends on the Claude Code CLI, which needs the user's own access and may change its flags | Pin a tested version in `doctor` and document it |
| A scheduled run does not fire while the computer is asleep | Say so in the README, and run missed schedules at the next start |

**Assumptions.** The first development and test machine is a Mac. Python 3.11 or later, Node 18 or later and Chrome are installed. The user has Claude Code access. The user creates accounts and signs in themselves.
