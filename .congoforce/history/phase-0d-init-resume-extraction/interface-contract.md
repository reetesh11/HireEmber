# Interface contract — phase-0d-init-resume-extraction

### `hireember.resume_extract` (new)
- `MIN_TEXT_CHARS = 200`
- `extract_pdf_text(path: str | Path) -> str` — returns all pages' text joined with `"\n"` via pypdf. Never raises: any failure (corrupt, empty, image-only, encrypted that cannot be decrypted with an empty password, unreadable) returns `""`. Local only, no network.
- `propose_profile(text: str) -> dict[str, str]` — returns only confidently found fields; keys are a subset of `full_name`, `email`, `phone`, `linkedin_url`, `city`, `province_state`, `country`. Never returns postal code. Rules:
  - `email`: exactly one distinct email address in the text, else absent.
  - `phone`: exactly one distinct phone number (7 to 15 digits, ignoring spaces, dashes, dots, parentheses, leading +), returned as written in the resume; two different numbers means absent.
  - `linkedin_url`: exactly one distinct `linkedin.com/in/<slug>` match, returned as written (including `https://`/`www.` if present); otherwise absent.
  - `full_name`: the first non-empty line, only if it has 2 to 4 words, all letters (plus `-`, `'`, `.`), with no digits, `@` or `/`; otherwise absent.
  - `city`, `province_state`, `country`: from the first 10 non-empty lines; split a line on `|`, `•`, `·` into segments; a segment with exactly three non-empty comma-separated parts and no digits gives the three values (stripped). Zero or more than one such segment, or a two-part header like "Toronto, Ontario", gives none of the three.
  - Malformed input (empty string, binary-ish text) returns `{}`; no exceptions.

### `hireember.wizard.init`
- `run_resume_step(conn, ask: Callable[..., str] | None = None, *, console: Console | None = None) -> None` — step 1. Default `ask` is `Prompt.ask(escape(question), console=out, **kwargs)`. Uses `config.RESUME_PATH`, `config.RESUME_PDF_PATH` (read at call time via module attribute so tests' `HIREEMBER_DIR` isolation works as `run_profile_step` does). Questions passed to `ask`, exact strings:
  - `"Resume file path"` — reply is stripped, outer quotes removed, `~` expanded. Missing: prints `File not found: <path>`, re-asks. Wrong extension: prints `Unsupported format. Provide a .txt or .pdf file.`, re-asks.
  - `"resume.txt already exists. Overwrite it? [y/N]"` — asked only when `resume.txt` exists, is user-supplied (see marker rule), and the new file would replace it. Reply `y`/`yes` (case-insensitive) replaces; anything else leaves it byte-for-byte unchanged. Declined: step continues with the existing `resume.txt` (a chosen .pdf is still copied to `resume.pdf`).
  - `"Resume .txt file path"` — asked after printing `Could not read any text from <filename>. It may be a scanned image, password-protected, or damaged. Please give a plain-text (.txt) version of your resume instead.` Non-.txt reply prints `Please provide a .txt file.` and re-asks; missing file prints `File not found: <path>` and re-asks.
  - `"Does this look right? [Y/n]"` — printed after: the first 10 non-empty lines of `resume.txt` (each truncated to 100 chars), `Characters read: <N>` (N = `len` of `resume.txt` text), and `Saved as <full path of resume.txt> (you can edit this file).` Reply `n`/`no` re-asks `"Resume file path"` (no abort, no registration); anything else confirms.
  - Result files: `.txt` source gives `resume.txt` (copy, bytes preserved, `resume.pdf` not created). `.pdf` source with at least 200 extracted chars gives `resume.pdf` (copy) and `resume.txt` (UTF-8 extracted text). A text-less PDF writes neither file.
  - After confirmation, registers "Master resume" (see Approach): `.pdf` run registers `resume.pdf` with `text_file=resume.txt`; `.txt` run registers `resume.txt`. Two consecutive runs leave exactly one entry in `list_resumes(conn)`, no exception, no error output.
  - Never raises for any bad PDF or bad input path; Ctrl+C (KeyboardInterrupt from `ask`) propagates.
- `run_profile_step(conn, ask=None, *, console=None) -> dict` — same signature and return as today. New behaviour: reads `config.RESUME_PATH` (if it exists; `errors="replace"`), calls `propose_profile`. For a question in the contact or location groups that has a proposal AND no stored profile answer, it calls `ask(question, default=<proposal>)`; the default `ask` wrapper forwards `default=` to `Prompt.ask`, so Enter accepts. A reply is stripped; empty reply with default is impossible (rich returns the default). Questions without a proposal are called as `ask(question)` with no kwargs, exactly as before. The "Keep your <group> answers? [Y/n]" prompt and the blank re-ask message are unchanged. Stored answers are never overwritten by proposals, including after the user answers `n` to keep (the stored value gets no proposal, no default). A missing or unreadable `resume.txt` gives no proposals.
- `run_wizard()` — calls `conn = init_db()`, `run_resume_step(conn)`, then `run_profile_step(conn)`; steps 3 to 5 unchanged. The old private `_setup_resume` is removed.
- Scripted test `ask` callables receive `(question, **kwargs)`; tests read `kwargs.get("default")` to see the proposed default.

### CLI / doctor
- `hireember init` runs the new flow. `hireember resume list` shows one "Master resume" row after init (twice).
- `hireember doctor`: with `resume.txt` present, the row is `resume.txt  OK  <path>`; "Only PDF found" does not appear. Other rows unchanged.

### Dependency
- `pypdf>=4.0` added to `[project].dependencies` in `pyproject.toml` (version, authors, urls untouched; the pyproject-unchanged acceptance test only checks those).
