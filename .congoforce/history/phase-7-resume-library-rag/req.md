---
class: feature
size: large
title: Resume library with .docx upload and local searchable context store
---
# Requirements — Resume library with .docx upload and local searchable context store

## Problem
The user can add base resumes only as `.txt` or `.pdf` from the CLI, and the dashboard can only replace the file of an existing resume. They want to upload several resumes (including `.docx`) from the dashboard, have the text extracted and kept locally as sections and chunks, and have scoring, tailoring and applying pull the most relevant chunks as extra context. Nothing leaves the machine except the prompts the pipeline already sends.

## Requirements
- R1. When the user uploads a `.pdf`, `.txt` or `.docx` file with a name and optional tags (dashboard or CLI), the system shall create a resume (RES-1, RES-2).
- R2. When a resume is created or its file replaced, the system shall extract plain text, split it into sections and bounded chunks, and store both locally (RES-3).
- R3. When a query is given, the system shall return ranked chunks with resume and section, across one resume or all (RES-4).
- R4. When scoring, tailoring or form-filling builds a prompt and the resume has chunks, the system shall add up to N retrieved chunks; if there are none, the prompt shall be unchanged (RES-5).
- R5. While a resume is listed, the system shall show its extraction state and chunk count, and let the user re-run extraction (RES-6).
- R6. When a resume is deleted, the system shall remove its file, text copy and chunks (RES-7).
- R7. If the upload has a bad extension, is empty or exceeds 10 MB, then the system shall refuse it in plain language and store nothing.

## Acceptance criteria
- AC-1: `POST /api/resumes` (multipart, or raw body with `X-Filename`) creates a resume from `.pdf`, `.txt` or `.docx` with a name and tags. Other extensions, empty files and files over 10 MB return a plain-language error and store no file and no row.
- AC-2: The Resumes tab has an "Add resume" form (file, name, tags). Several resumes can be added one after another and the list updates without a page reload.
- AC-3: `hireember resume add <file>` accepts `.docx`. Text is extracted from paragraphs and tables using a documented dependency (for example `python-docx`) added to `pyproject.toml` and `uv.lock`. CLI help text (`typer.Typer(help=...)` and callback docstring) mentions the formats.
- AC-4: Extraction writes (a) a plain-text copy next to the stored file that `get_resume_text` reads, and (b) sections (summary, experience, education, skills, other; found by headings, falling back to one section) split into chunks of bounded size, each with section name, resume id and position.
- AC-5: Chunks live in a SQLite `resume_chunks` table created by a migration. Retrieval is keyword ranked (FTS5 or BM25 style) and works offline. Any embedding backend is optional, offline and off by default.
- AC-6: `resumes.search(conn, query, resume_id=None, limit=5)` returns ranked chunks (with resume id and section). An empty or blank query, or an empty store, returns `[]` without error. "Python experience" ranks a chunk containing "Python" above one that does not.
- AC-7: Tailoring, scoring and the apply prompt include up to N retrieved chunks (default 5, configurable) for the job. For a resume with no chunks the prompts are byte-identical to today; existing tests pass unchanged. New tests show chunks reach each prompt.
- AC-8: Each resume row shows extraction status (extracted, failed with reason, scanned PDF with no text) and chunk count. Failed or empty extraction shows the reason and a "Re-extract" button that re-runs extraction. Replacing a resume's file re-runs extraction.
- AC-9: Deleting a resume removes the stored file, text copy and all its chunks, leaving no orphans. A resume used by a ticket is still blocked from deletion with the existing message.
- AC-10: Uploaded filenames are sanitized (no path parts, e.g. `../../x.pdf` is stored inside the app data folder only). No resume text is logged above debug level. The phase 6 key and telemetry scans still pass.
- AC-11: Resume name uniqueness, pin, unpin and choose-best-resume behave as before (existing tests pass unchanged).
- AC-12: README and `docs/traceability.md` list RES-1..RES-7, supported formats, and a privacy note that extraction is fully local.

## Out of scope
- Remote vector databases or hosted embedding services.
- Parsing resumes into a full structured profile (phase 0d init extraction unchanged).
- OCR for scanned PDFs (clear message only).
- Legacy `.doc`, `.rtf`, `.odt`.
- Indexing the answer bank (unless the human decides otherwise below).

## Assumptions
- Keyword retrieval via FTS5 is the default; SQLite in the project's Python build has FTS5 available.
- Chunk size is a bounded value chosen in the tech spec (about 500-800 characters); default N is 5.
- Existing resumes get chunks on first re-extract or via the migration; no automatic backfill is required.
- The extraction status is stored per resume (column or table chosen in tech spec).

## Suggested split
1. Formats and extraction: `.docx` support in CLI, `POST /api/resumes` upload with validation and filename sanitising, sections and chunks, `resume_chunks` migration, status, re-extract, delete cleanup (AC-1, 3, 4, 5, 8 backend, 9, 10, 11).
2. Retrieval and prompt context: `resumes.search`, N setting, injection into scoring, tailoring and apply prompts with byte-identical fallback (AC-6, 7).
3. Dashboard: Add resume form, status, chunk count, Re-extract button, list refresh (AC-2, 8 UI).
4. Docs: README and traceability (AC-12), can ship with the last part.

## Open questions
- Confirm retrieval method: keyword (FTS5) by default, embeddings only as an optional offline extra?
- Confirm chunk size and default N (assumed ~500-800 characters and 5)?
- Should the phase 2 answer bank also be indexed in this store? (Default: no.)
- Should the large split above be approved, and which part runs first?
