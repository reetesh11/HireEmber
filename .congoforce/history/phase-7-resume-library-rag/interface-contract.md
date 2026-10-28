# Interface contract — phase-7-resume-library-rag

### Python API (`hireember.resumes`)
- `ResumeError(Exception)` (existing). Messages (exact):
  - `"Unsupported format. Provide a .pdf, .txt or .docx file."` (replaces the old `.txt or .pdf` text everywhere)
  - `"The file is empty."`, `"The file is larger than 10 MB."` (limit `MAX_UPLOAD_BYTES = 10 * 1024 * 1024`; exactly that size is accepted)
  - `"Name cannot be empty."`, `'A resume named "<name>" already exists.'`
  - `'Resume "<name>" is used by N ticket(s) and cannot be deleted.'`
  - `"No resume with id <id>."`
- `add_resume(conn, file, name, tags="", text_file=None) -> int` — as today, now accepts `.docx`, rejects empty / over-10 MB files and blank names, and runs extraction after storing. Extraction problems never raise: the resume is kept with a failed or no_text status.
- `add_resume_bytes(conn, filename: str, data: bytes, name: str, tags: str = "") -> int` — validates in the order extension, empty, size, name, duplicate; `filename` is reduced to its base name (both `/` and `\` separators dropped) and only its extension is used. Stores nothing on any refusal.
- `update_resume(conn, resume_id, file, text_file=None) -> None` — as today (accepts `.docx`, same validation), then re-extracts; old chunks are replaced.
- `replace_resume_file_bytes(conn, resume_id, filename: str, data: bytes) -> None` — bytes variant of the above, same validation.
- `extract_resume(conn, resume_id) -> ExtractResult` — re-runs extraction, replaces all chunks, stores status. `ExtractResult` is a dataclass with `status: str`, `reason: str`, `chunks: int`. Never raises for file problems. Raises `ResumeError("No resume with id <id>.")` for unknown id.
  - `status` values: `"extracted"`, `"failed"`, `"no_text"`.
  - Reasons: `"this .docx file could not be read."`, `"this PDF could not be read."`, `"The stored file is missing. Replace the file."`, `"this looks like a scanned PDF. OCR is not supported. Add a text copy or a text-based PDF."` (no_text for PDF), `"the file has no text."` (no_text for txt/docx). Reasons never contain file content or stack traces.
- `list_resumes(conn) -> list[dict]` — existing keys plus `extract_status` (`"extracted"|"failed"|"no_text"|"not_extracted"`; `"not_extracted"` for rows with no status), `extract_reason: str` (`""` if none) and `chunk_count: int`.
- `delete_resume(conn, resume_id) -> None` — removes the stored file, its `.txt` copy (for `.pdf`/`.docx`), all `resume_chunks` rows and their FTS entries, then the row. Refuses with the "is used by N ticket(s)" error when `tickets.resume_id` references it (nothing removed). Unknown id: `ResumeError("No resume with id <id>.")`.
- `search(conn, query: str, resume_id: int | None = None, limit: int = 5) -> list[dict]` — ranked, best first. Each dict has `chunk_id`, `resume_id`, `resume_name`, `section`, `position`, `text`, `score` (float, higher is better). `[]` for a blank or whitespace query, a query with no word characters, an empty store, `limit <= 0`, or an unknown `resume_id`. Never raises for FTS special characters (`" * - : ( ) ^ AND OR NEAR`). Terms are OR-matched and BM25 ranked, so a chunk containing "Python" ranks above one without it for "Python experience".
- `context_block(conn, resume_id: int, job: dict, n: int | None = None) -> str` — query is built from `job["title"]` and the first 2000 characters of `job.get("full_description")`. `n` defaults to the integer setting `resume_context_chunks` (default 5; non-numeric or < 1 falls back to 5). Returns `""` when the resume has no chunks or nothing matches. Otherwise returns text starting `RELEVANT RESUME EXCERPTS (best matches for this job):\n` followed by one line per chunk `[<section>] <text with newlines collapsed to spaces>`, joined by `\n`, with no trailing newline. At most n chunks.
- `get_resume_text`, `choose_resume`, `pin_resume`, `unpin_resume`, `update_resume_meta` unchanged in behaviour.

### Python API (`hireember.resume_index`)
- `SECTIONS = ("summary", "experience", "education", "skills", "other")`
- `MAX_CHUNK_CHARS = 800`
- `split_sections(text: str) -> list[tuple[str, str]]` — `(section, body)` in document order. Heading lines (case-insensitive, whole line, optional trailing colon, e.g. "Professional Summary", "Summary", "Profile", "Work Experience", "Experience", "Employment", "Education", "Skills", "Technical Skills") start a section. Text before the first heading goes to `summary` if there is no heading before it and it is at most 600 characters, otherwise `other`. With no headings, one section `other`. Empty sections are dropped.
- `chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]` — packs whole paragraphs/lines into chunks of at most `max_chars`; a single over-long line is split on whitespace. No empty chunks. Whitespace-only text returns `[]`.
- `replace_chunks(conn, resume_id: int, text: str) -> int` — deletes the resume's chunks, inserts new ones (0-based `position` over the whole resume), returns the count.
- `delete_chunks(conn, resume_id: int) -> None`
- `count_chunks(conn, resume_id: int) -> int`
- `search_chunks(conn, query, resume_id=None, limit=5) -> list[dict]` — same result shape and rules as `resumes.search`.

### Python API (`hireember.resume_extract`)
- `extract_docx_text(path) -> str` — body paragraphs and table cells in document order; cells in a row joined by a tab, rows and paragraphs by newlines. Raises `ValueError("this .docx file could not be read.")` on corrupt/unreadable files.
- `extract_pdf_text(path)` unchanged (returns `""` on failure).

### Prompt hooks
- `hireember.scoring.scorer.score_job(resume_text, job, profile=None, resume_context: str = "")`. When non-empty, the user message becomes `RESUME:\n{resume_text}\n\n---\n\n{resume_context}\n\n---\n\n{preferences}JOB POSTING:...`. When empty the message is byte-identical to today.
- `hireember.scoring.tailor.tailor_resume(resume_text, job, profile, max_retries=3, validation_mode="normal", resume_context: str = "")`. When non-empty, the user message is `ORIGINAL RESUME:\n{resume_text}\n\n---\n\n{resume_context}\n\n---\n\nTARGET JOB:...`. Empty: byte-identical.
- `hireember.apply.prompt.build_prompt(job, tailored_resume, cover_letter=None, dry_run=False, resume_context: str = "")`. When non-empty, a block `== RESUME EXCERPTS (from your base resume, reference only) ==\n{resume_context}\n\n` is inserted immediately after the `== RESUME TEXT (reference only) ==` block (after `{tailored_resume}` and its blank line) and before `== COVER LETTER TEXT`. Empty: byte-identical.
- `gating.score_job_for_ticket` and `gating.tailor_ticket` pass `resumes.context_block(conn, resume_id, job)` as `resume_context`. `apply.launcher.run_job` and `gen_prompt` pass the block for the ticket's `resume_id` (none/no ticket resume: `""`).

### CLI (`hireember resume ...`)
- `resume_app` help: `"Base resumes (.pdf, .txt, .docx) used for scoring and tailoring."`
- `resume add FILE --name NAME [--tags T] [--text PATH]`: file argument help `"Resume file (.pdf, .txt or .docx)."`; command docstring and `help` `"Add a base resume (.pdf, .txt or .docx)."`. Output: `Added resume <id>: <name>.`; then, when status is extracted, `Extracted <N> chunks.`; otherwise `Added, but no text could be extracted: <reason>` (exit code 0). Unsupported extension: prints `Unsupported format. Provide a .pdf, .txt or .docx file.`, exit 1.
- `resume list`: table gains columns `Extraction` (`Extracted`, `Failed: <reason>`, `No text found: <reason>`, `Not extracted`) and `Chunks`.
- `resume delete RESUME_ID`: prints `Deleted resume <id>.`; errors printed, exit 1.

### HTTP (dashboard server)
Resume JSON object (used in `GET /api/resumes` -> `{"resumes": [...]}` and responses below): `{"id", "name", "tags": [..], "pinned": bool, "file_name", "extract_status", "extract_reason", "chunk_count"}`.
- `POST /api/resumes` — either
  - raw body (file bytes) with headers `X-Filename`, `X-Name`, `X-Tags` (optional); header values are percent-decoded (UTF-8), or
  - `multipart/form-data` with parts `file` (filename taken from the part), `name`, `tags` (optional).
  Success: `201` with the resume object. Failure: `400` with `{"error": "<message>"}` for the messages above (unsupported, empty, blank name, duplicate); a body larger than 10 MB + 64 KB is refused with `413` and `{"error": "The file is larger than 10 MB."}`; a file over 10 MB inside that margin gives `400` with the same message. Nothing stored on any failure. Stored name derives from the resume name, never from the client filename.
- `POST /api/resumes/<id>/extract` (empty or `{}` body) — `200` `{"ok": true, "message": "Extraction finished: N chunks.", "resume": {...}}` when status is extracted; otherwise `200` `{"ok": false, "message": "Extraction failed: <reason>", "resume": {...}}`. Unknown id: `404`.
- `POST /api/resumes/<id>/file` — as today (raw body, `X-Filename`), now accepts `.docx`, validates, re-extracts; `200` `{"ok": true, "message": "Resume file replaced.", "resume": {...}}`.
- `DELETE /api/resumes/<id>` — `200` `{"ok": true}`; used by a ticket: `400` with the "is used by N ticket(s)" message; unknown: `404`.
- Same host/origin guard as other write routes (`_WRITE_METHODS`).

### UI (`web/static/index.html`, Resumes tab)
- Always-visible form above the list, labelled controls: `File` (input type=file, `accept=".pdf,.txt,.docx"`, aria-label "File"), `Name` (aria-label "Name"), `Tags` (aria-label "Tags"), submit button text `Add resume` (`Adding...` and disabled while uploading). Success toast `Resume added.`, form cleared, list refreshed without reload. Failure text appears in the `role="alert"` message element; form values kept.
- Empty state text: `No resumes yet. Add one with the form above or with 'hireember resume add'.`
- Table headers: `Name`, `Tags`, `Pinned`, `File`, `Extraction`, `Chunks`, and an action column. Extraction cell text: `Extracted`, `Failed: <reason>`, `No text found: <reason>`, `Not extracted`. Chunks cell: integer. Every row has buttons `Re-extract`, `Replace file` (accept `.pdf,.txt,.docx`), `Edit`, `Delete` (asks `window.confirm` first). Toasts: `Extraction finished: N chunks.` / `Extraction failed: <reason>`, `Resume file replaced.`, `Resume deleted.`.
