# Product spec — Resume library with .docx upload and local searchable context store

Product name in user-facing copy is HireEmber (CLI `hireember`). Decisions from Gate 1 (answers.md): FTS5 keyword retrieval only, chunks of about 500-800 characters, N = 5, answer bank not indexed, one task.

## User-facing behaviour

### Current surface (for reference)
- CLI: `hireember resume add <file> --name ... [--tags] [--text]`, `resume list`, `resume pin`, `resume unpin`. Today `add` accepts `.txt` and `.pdf` only, with the error "Unsupported format. Provide a .txt or .pdf file."
- Dashboard Resumes tab (`src/hireember/web/static/index.html`, `renderResumes`): a table with columns Name, Tags, Pinned, File and per-row Edit and "Replace file" buttons. With no resumes it shows "No resumes yet. Add one with 'hireember resume add'."
- No resume delete exists in the CLI, API or dashboard today (see Open questions).

### Adding a resume from the dashboard
1. The Resumes tab shows an "Add resume" form above the list, always visible, including when the list is empty. Fields: File (file picker accepting `.pdf,.txt,.docx`), Name (text, required), Tags (text, optional, comma separated, same normalisation as today). Submit button: "Add resume".
2. On submit the file is uploaded. While uploading the button is disabled and reads "Adding...".
3. On success a toast reads "Resume added." The form clears, and the new row appears in the list without a page reload. The user can immediately add another.
4. On failure the form keeps its values (except the file may need re-picking) and shows the plain-language error in the existing alert area above the table (`role="alert"`). Nothing is stored.
5. The empty-state text changes to "No resumes yet. Add one with the form above or with 'hireember resume add'."

### Resume list
Columns become: Name, Tags, Pinned, File, Extraction, Chunks, actions.
- Extraction cell shows one of:
  - "Extracted" (text found, chunks stored)
  - "Failed: <reason>" (for example "Failed: this .docx file could not be read.")
  - "No text found: this looks like a scanned PDF. OCR is not supported. Add a text copy or a text-based PDF."
  - "Pending" is not a user-visible state; extraction runs synchronously during upload.
- Chunks cell shows the integer count (0 when failed or empty).
- Rows with Failed or No text found also show a "Re-extract" button. Rows with Extracted also show "Re-extract" (harmless, same action) so users can refresh after a code update; the button is prominent only for failed/empty rows.
- "Re-extract" success toast: "Extraction finished: N chunks." If it still fails the row shows the new reason and the toast reads "Extraction failed: <reason>".
- "Replace file" accepts `.pdf,.txt,.docx`, re-runs extraction automatically, and updates the row. Toast: "Resume file replaced."
- Existing Edit, Pin behaviour is unchanged.

### Delete
Deleting a resume (see Open questions for the entry points) removes the stored file, the plain-text copy and all chunk rows, then the row disappears. If any ticket uses the resume, deletion is refused with the message: `Resume "<name>" is used by N ticket(s) and cannot be deleted.` (proposed wording, to be confirmed; no existing message was found in the code).

### CLI
- `hireember resume add <file> --name <name> [--tags ...]` accepts `.txt`, `.pdf` and `.docx`.
- Typer app help: "Base resumes (.pdf, .txt, .docx) used for scoring and tailoring." The `add` command help and callback docstring list the formats: "Add a base resume (.pdf, .txt or .docx)." The `file` argument help: "Resume file (.pdf, .txt or .docx)."
- Success line unchanged: `Added resume <id>: <name>.` After it, when extraction succeeded, a second line: `Extracted N chunks.` If extraction found no text or failed, the resume is still added and the line reads `Added, but no text could be extracted: <reason>` (a stored file with failed extraction is allowed; the user can fix via re-extract or replace).
- Unsupported extension error: "Unsupported format. Provide a .pdf, .txt or .docx file."
- `resume list` gains Extraction and Chunks columns.
- `hireember resume search "<query>" [--resume ID] [--limit N]` is not required (the function is the deliverable); not added.

### Retrieval and prompt context
- Retrieval is invisible to the user except through better prompts. For a job, scoring, tailoring and the apply (form-filling) prompt each append a clearly labelled block of up to N chunks (default 5) from the relevant resume, ranked against the job (title, description). The setting for N is configurable in the existing config; the label wording is fixed in tech-spec but must name the resume section for each chunk.
- If the resume has no chunks, or the query yields no matches, no block is added and the prompt is byte-identical to today.
- Nothing is sent anywhere new. Extraction and indexing are fully local.

## Acceptance criteria

- AC-1: `POST /api/resumes` creates a resume from a `.pdf`, `.txt` or `.docx` upload, either `multipart/form-data` (fields `file`, `name`, `tags`) or a raw body with headers `X-Filename` and, for name and tags, `X-Name` and `X-Tags` (exact header names finalised in tech-spec; `name` required, `tags` optional). Success returns 201 with the resume as in `GET /api/resumes` including extraction status and chunk count. Refusals return 4xx with `{"error": "<message>"}`, store no file and no row, and use these messages:
  - Extension not in `.pdf`, `.txt`, `.docx` (case-insensitive): "Unsupported format. Provide a .pdf, .txt or .docx file."
  - Empty file (0 bytes): "The file is empty."
  - Over 10 MB (10 x 1024 x 1024 bytes; exactly 10 MB is accepted): "The file is larger than 10 MB."
  - Missing or blank name: "Name cannot be empty."
  - Duplicate name: `A resume named "<name>" already exists.` (existing message)
- AC-2: The Resumes tab has an "Add resume" form (File, Name, Tags, button "Add resume") as described above. Several resumes can be added one after another and the list updates after each without a page reload.
- AC-3: `hireember resume add <file>` accepts `.docx`. Text is extracted from body paragraphs and table cells (in document order where practical; table cells joined by tabs or spaces, rows by newlines). The dependency (for example `python-docx`) is in `pyproject.toml` and `uv.lock`. Help text per CLI section above. A corrupt `.docx` still creates the resume with status "Failed: <reason>" via CLI, and via the API (resume row stored, status failed), because the file itself passed validation. (Only extension, empty and size checks block storage.)
- AC-4: Extraction writes (a) a plain-text copy next to the stored file (`<stored name>.txt`, or for a `.txt` upload the file itself) which `get_resume_text` reads, and (b) sections named `summary`, `experience`, `education`, `skills`, `other`, found by heading lines (case-insensitive, for example "Professional Summary", "Work Experience", "Education", "Skills"); text before the first heading goes to `summary` if no heading precedes it and it is short, otherwise `other`; if no headings are found the whole text is one section (`other`). Each section is split into chunks of at most about 800 characters (target 500-800), splitting on paragraph or line boundaries where possible. Each chunk stores resume id, section name and position (0-based order within the resume). Re-extraction replaces the resume's previous chunks entirely.
- AC-5: Chunks live in the SQLite `resume_chunks` table, created by a migration, with an FTS5 index for keyword ranking (BM25). Works with no network. No embedding backend is shipped or enabled.
- AC-6: `resumes.search(conn, query, resume_id=None, limit=5)` returns a list of ranked chunks, best first, each carrying at least resume id, resume name, section, position and text. `resume_id=None` searches all resumes. Empty or whitespace-only query, a query with no usable terms (for example only punctuation), or an empty store returns `[]` with no exception. "Python experience" ranks a chunk containing "Python" above one that does not. `limit` caps the result count. Queries containing FTS special characters (quotes, `*`, `-`, `:`) never raise.
- AC-7: Tailoring, scoring and the apply prompt include up to N retrieved chunks (default 5, configurable in the existing config) for the job. The chunks come from the resume being used for that step. For a resume with no chunks, prompts are byte-identical to today and existing tests pass unchanged. New tests show chunks reach each of the three prompts.
- AC-8: Each resume row shows extraction status (Extracted, Failed with reason, No text found for a scanned PDF) and chunk count. Failed or empty rows show the reason and a "Re-extract" button that re-runs extraction (API: `POST /api/resumes/<id>/extract`, path finalised in tech-spec). Replacing a resume's file re-runs extraction. Existing resumes created before this change show "Not extracted" with 0 chunks until re-extracted (no automatic backfill) and offer "Re-extract".
- AC-9: Deleting a resume removes the stored file, the text copy and all its chunks (including FTS entries), leaving no orphans. A resume used by a ticket remains blocked from deletion.
- AC-10: Uploaded filenames are sanitised: any directory part (`../../x.pdf`, `C:\a\b.docx`) is dropped, so files are written only inside the app data folder, under the name derived from the resume name as today. Resume text and chunk content is never logged above debug level (not in info, warning or error messages, and not in API error bodies). The phase 6 key scan and telemetry scan still pass.
- AC-11: Resume name uniqueness, pin, unpin and choose-best-resume behave as before; existing tests pass unchanged.
- AC-12: README and `docs/traceability.md` list RES-1 to RES-7, the supported formats (`.pdf`, `.txt`, `.docx`; no OCR), the 10 MB limit, and this privacy note: "Resume text extraction and search run entirely on your machine. Resume text leaves it only inside the prompts the pipeline already sends to your configured model."

## Edge cases and errors
- Scanned or image-only PDF: resume is stored, status "No text found: this looks like a scanned PDF...", chunks 0, Re-extract shown, prompts unchanged. `get_resume_text` keeps its existing no-text behaviour for such resumes.
- PDF text extraction currently relies on the `--text` copy via the CLI; for dashboard PDF uploads the system extracts text locally from the PDF. If that cannot be done, status is Failed with a reason.
- Password-protected or corrupt file: stored, status "Failed: <short reason>"; no stack traces or file content in the message.
- Non-UTF-8 `.txt`: decoded with a lenient fallback; undecodable bytes are replaced, not fatal.
- Whitespace-only `.txt`/`.docx`: status "No text found", 0 chunks.
- Very long resumes produce many chunks; no upper limit is shown.
- Same file uploaded under two names: allowed (names are the unique key).
- Filename without extension or with double extension (`cv.docx.exe`): refused as unsupported.
- Upload interrupted or server error: nothing stored; leftover partial files are removed.
- Re-extract on a resume whose stored file has gone missing: status Failed "The stored file is missing. Replace the file."
- Extraction on replace failing: the old file is replaced and the status shows the failure (old chunks removed so stale content is not used).
- Unauthorised: dashboard write endpoints keep their existing protections (`_WRITE_METHODS` handling); the new endpoints get the same treatment.
- Double submit of the form: the button is disabled while in flight; a second duplicate name gives the duplicate-name error.

## Out of scope
- Remote vector databases or hosted embedding services; any embedding backend.
- Parsing resumes into a full structured profile (phase 0d init extraction unchanged).
- OCR for scanned PDFs (message only).
- Legacy `.doc`, `.rtf`, `.odt`.
- Indexing the answer bank.
- Automatic backfill of existing resumes.
- A CLI `resume search` command.

## Open questions
- Resume delete does not exist today in the CLI, API or dashboard, and no "existing message" for a resume used by a ticket was found in the code. AC-9 needs an entry point. Proposal: add `hireember resume delete <id>`, `DELETE /api/resumes/<id>` and a "Delete" button with a confirm, with the message `Resume "<name>" is used by N ticket(s) and cannot be deleted.` Confirm, or name the existing message if it lives elsewhere.
- For PDFs uploaded via the dashboard (no `--text` copy), is local PDF text extraction (a library dependency) in scope, or must a PDF without a text copy show "No text found"? The spec above assumes local extraction is done.
- Should a failed extraction on upload still store the resume (as specified) or refuse it?
