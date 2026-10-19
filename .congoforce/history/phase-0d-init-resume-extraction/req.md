---
class: feature
size: medium
title: Make hireember init read the resume and pre-fill the profile
---
# Requirements — Make hireember init read the resume and pre-fill the profile

## Problem
`hireember init` asks PDF users for a separate plain-text resume, which most do not have. The data folder then lacks `resume.txt`, the cover letter stage crashes, and scoring blocks every job with "no base resume" because init never registers the resume. The profile step also asks for contact and location details that are already in the resume.

## Requirements
- R1. The system shall add `pypdf` as a dependency and extract PDF text locally, sending nothing to any service.
- R2. When init step 1 runs, the system shall ask for one resume file (.pdf or .txt) and not ask for a separate plain-text file.
- R3. When given a .txt, the system shall copy it to the data folder as `resume.txt`.
- R4. When given a .pdf, the system shall copy it as `resume.pdf`, extract its text and save it as `resume.txt`.
- R5. If the data folder already holds a user-supplied `resume.txt`, then on a re-run the system shall ask before overwriting it.
- R6. After extraction, the system shall show the first lines of the text, the character count, and the path of `resume.txt` (stating it is editable), and ask the user to confirm.
- R7. If a PDF yields no usable text (fewer than about 200 characters; empty, image-only, encrypted or corrupt), then the system shall say so in plain words, ask for a .txt path instead, and continue without an unhandled exception.
- R8. When step 1 completes, the system shall register the resume in the base resume registry used by `hireember resume add`, without creating a duplicate on re-run.
- R9. When the profile step runs, the system shall read `resume.txt` and propose, only when found with confidence: full name, email, phone, LinkedIn URL, and city, province/state, country (from a "City, Province/State, Country" header line).
- R10. While asking a question that has a proposal, the system shall show it as the default (Enter accepts, typing replaces) and store the final value in the answer bank as today.
- R11. If a field is not found with confidence, then the system shall ask it without a default and never invent a value.
- R12. While answers are already stored from an earlier run, the system shall keep them and never replace them with resume values.
- R13. The system shall ask questions the resume cannot answer (work authorization, salary, EEO, start date, etc.) as before.
- R14. When `resume.txt` exists after init, `hireember doctor` shall not report "Only PDF found"; no other doctor check changes.
- R15. The system shall do pre-filling without an LLM, so it works before an API key is configured.

## Acceptance criteria
- AC-1: `pytest` and `ruff check .` pass.
- AC-2: Given a text-based PDF fixture, init step 1 leaves `resume.pdf` and a non-empty `resume.txt` containing the fixture's words, without prompting for a text file.
- AC-3: Given a .txt resume, init copies it to `resume.txt` and asks nothing else about the file.
- AC-4: Given an image-only PDF, an empty PDF, and a corrupt file named `.pdf`, init prints that no text could be read, asks for a .txt path, and finishes step 1 with no unhandled exception once a .txt path is given.
- AC-5: After step 1, the resume appears in `hireember resume list`; running init twice leaves one entry.
- AC-6: Given a fixture resume with known name, email, phone, LinkedIn URL and "City, Province, Country" header, the profile step offers exactly those values as defaults; pressing Enter on each stores them in the answer bank and `profile.json`.
- AC-7: Given a resume lacking some of those fields, the missing ones are asked with no default and no value is invented.
- AC-8: Given stored profile answers from an earlier run, a re-run keeps them and does not replace them with resume values.
- AC-9: After accepting the AC-6 defaults with `resume.txt` produced from the PDF, `hireember doctor` shows the resume row as OK.
- AC-10: Re-running init with an existing user-supplied `resume.txt` asks before overwriting it; declining keeps the file unchanged.
- AC-11: Step 1 output includes the first lines of the text, the character count, and the `resume.txt` path, then asks for confirmation.
- AC-12 (unchanged behaviour): profile questions not answerable from the resume, and the search config, AI and auto-apply steps, behave as before.

## Out of scope
- OCR for scanned PDFs.
- Using an LLM to read the resume or fill the profile.
- Pre-filling skills, years of experience, education or target roles.
- Changes to scoring, tailoring or the cover letter stage, and other first-run items (preflight checks, honest stage results, Playwright install, discovery timeouts).

## Assumptions
- The ~200 character threshold counts non-whitespace-trimmed extracted text length.
- Declining the confirmation in R6 re-asks for a resume file (or .txt path) rather than aborting init.
- Registration reuses `resumes.add_resume` in `src/hireember/resumes.py`; wizard code lives in `src/hireember/wizard/init.py`; the doctor message is in `src/hireember/doctor.py`.

## Open questions
- none
