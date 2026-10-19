# Product spec — Make hireember init read the resume and pre-fill the profile

## User-facing behaviour

Existing surface: `hireember init` runs five steps (`src/hireember/wizard/init.py`): 1 Resume, 2 Profile (ten groups, answer bank, `profile.json`), 3 Search config, 4 AI, 5 Auto-Apply. `hireember resume list/add` use the base resume registry. `hireember doctor` has a `resume.txt` row. Only steps 1 and 2 change, plus one doctor message.

### Step 1: Resume
1. Panel text stays "Step 1: Resume" with "Point to your master resume file (.txt or .pdf)." One prompt only: `Resume file path`. Quotes around the path are stripped, `~` expands. Missing file ("File not found: <path>") and wrong extension ("Unsupported format. Provide a .txt or .pdf file.") re-ask as today.
2. A `.txt` is copied to `<data folder>/resume.txt`. Nothing else is asked about the file, apart from the confirmation in step 5.
3. A `.pdf` is copied to `<data folder>/resume.pdf`. Its text is extracted locally (pypdf; nothing leaves the machine) and written to `<data folder>/resume.txt`. The user is never asked for a plain-text file in this case.
4. Overwrite guard: if `resume.txt` already exists and was supplied by the user (not produced by a previous PDF extraction), the wizard asks `resume.txt already exists. Overwrite it? [y/N]` before replacing it. Declining leaves `resume.txt` byte-for-byte unchanged; the new file is then not applied to `resume.txt` and step 1 continues with the existing file (shown and confirmed as in step 5). A `resume.txt` produced from a PDF on an earlier run is replaced without asking.
5. Confirmation: after `resume.txt` is in place the wizard prints
   - the first lines of the text (first 10 non-empty lines, each truncated to 100 characters),
   - `Characters read: <N>`,
   - `Saved as <full path of resume.txt> (you can edit this file).`
   then asks `Does this look right? [Y/n]`. Yes continues. No re-asks `Resume file path` (a .pdf or .txt) without aborting init.
6. Registration: when step 1 completes (after confirmation), the resume is added to the base resume registry through the same mechanism as `hireember resume add`, with its text version, so `hireember resume list` shows it and scoring can pick it. Name is "Master resume" (see Open questions). Re-running init never adds a second entry; on a re-run the existing entry is kept (or refreshed in place) rather than duplicated, and no "already exists" error is shown to the user.

### No usable text
A PDF yields "no usable text" when extraction returns fewer than 200 characters (empty, image-only, encrypted, corrupt, or unreadable for any other reason). The wizard prints, in plain words:
`Could not read any text from <filename>. It may be a scanned image, password-protected, or damaged. Please give a plain-text (.txt) version of your resume instead.`
and asks `Resume .txt file path`. Only a `.txt` is accepted there; any other extension gives "Please provide a .txt file." and re-asks. Once a .txt is given, flow continues as the .txt case (copy, confirm, register). No traceback is ever shown. The failed PDF's text is not written to `resume.txt`. `resume.pdf` is not left behind from a failed extraction (see Edge cases).

### Step 2: Profile
- Before asking the "Name and contact" and "Location" groups, the wizard reads `resume.txt` (no LLM, no network, works with no API key) and derives proposals only where it is confident:
  - Full name, email, phone, LinkedIn URL (Name and contact group).
  - City, province or state, country (Location group), from a header line of the form `City, Province/State, Country`.
- A question with a proposal shows it as the default, in the usual rich style: `What is your email address? (jane@example.com)`. Enter accepts it; typing replaces it. The final value is saved to the answer bank (source "profile") and written to `profile.json` exactly as today.
- A question with no confident proposal is asked exactly as today, no default, and a blank reply re-asks ("An answer is needed here.").
- Postal/ZIP code is never proposed. All other groups (work authorization, availability, compensation, experience, target roles, skills, resume facts, EEO) are asked as today.
- Stored answers win. If a group is fully stored the "Keep your <group> answers? [Y/n]" prompt appears as today and answering yes keeps everything. A stored answer is never replaced by a resume value; a question with a stored answer receives no resume proposal. If the user answers `n` and re-answers the group, resume proposals may appear only for questions that have no stored answer.
- Nothing is invented: a wrong or ambiguous candidate (for example two different emails, or no line matching the three-part location pattern) yields no proposal.

### Doctor
`hireember doctor`: when `resume.txt` exists the row is `resume.txt  OK  <path>` and the text "Only PDF found" does not appear. The other states ("Only PDF found" when only `resume.pdf` exists, MISSING when neither does) and all other checks are unchanged.

## Acceptance criteria
- AC-1: `pytest` and `ruff check .` both exit 0, including the new tests for this feature.
- AC-2: Given a text-based PDF fixture, step 1 leaves `<data folder>/resume.pdf` and a non-empty `resume.txt` containing the fixture's distinctive words. The prompts seen are the file path prompt and the confirmation only; no prompt for a text file.
- AC-3: Given a `.txt` resume (no existing `resume.txt`), `resume.txt` is a copy of it. Prompts seen: file path and the confirmation only; no overwrite prompt, no other file question. No `resume.pdf` is created.
- AC-4: Given (a) an image-only PDF, (b) an empty PDF, (c) a corrupt file named `x.pdf`, step 1 prints the "Could not read any text from ..." message, asks `Resume .txt file path`, and after a valid .txt path is given finishes step 1 (copy, confirm, register) with no exception. Same for encrypted PDFs. Extraction under 200 characters triggers this path; exactly 200 or more is accepted.
- AC-5: After step 1, `hireember resume list` shows exactly one entry for the resume. Running init (step 1) a second time leaves exactly one entry, with no error.
- AC-6: Given a fixture resume with known name, email, phone, LinkedIn URL and a `City, Province, Country` header, the profile step shows exactly those seven values as defaults for the matching questions (name, email, phone, LinkedIn, city, province/state, country). Pressing Enter on each stores them in the answer bank and in `profile.json` (`personal.full_name`, `email`, `phone`, `linkedin_url`, `city`, `province_state`, `country`). Postal code has no default.
- AC-7: Given a resume lacking some of these fields, each missing field is asked with no default, no value is stored for it until the user answers, and no placeholder or guess appears anywhere.
- AC-8: Given stored profile answers from an earlier run, a re-run keeps them (the "Keep your ... answers?" flow) and no stored answer is overwritten by a resume value, including when the user declines to keep a group.
- AC-9: After accepting the AC-6 defaults with `resume.txt` produced from the PDF, `hireember doctor` shows the `resume.txt` row as OK and does not print "Only PDF found".
- AC-10: Re-running init when a user-supplied `resume.txt` exists asks `resume.txt already exists. Overwrite it? [y/N]` before touching it. Answering no (or Enter) leaves the file unchanged byte for byte; answering yes replaces it.
- AC-11: Step 1 output includes the first lines of the extracted/copied text, `Characters read: <N>`, and the `resume.txt` full path with "you can edit this file", followed by the `Does this look right? [Y/n]` prompt. Answering `n` re-asks for a file and does not abort or register until a confirmed file exists.
- AC-12 (unchanged behaviour): Profile questions not answerable from the resume (postal code, work authorization, availability, compensation, experience, target roles, skills, resume facts, EEO), plus search config, AI and auto-apply steps, have the same prompts, defaults, validation and outputs as before.

## Edge cases and errors
- Text with 200 or more characters but only whitespace/garbage: length is counted on the extracted text as given; threshold is 200 characters (per req assumption, no stripping beyond what extraction returns). Open question below.
- Multi-page PDFs: all pages' text is joined with newlines.
- A failed PDF: no `resume.pdf` or `resume.txt` from it is left in the data folder; any pre-existing files from earlier runs are untouched.
- Re-run with a `.pdf` when `resume.txt` came from a previous extraction: replaced silently with new extraction; no overwrite prompt.
- Re-run with a user-supplied `resume.txt` and a new `.pdf`: overwrite prompt applies to `resume.txt`; if declined, `resume.pdf` is still copied but `resume.txt` stays.
- Duplicate registry entry on re-run: no error text, one entry.
- User declines confirmation repeatedly: loop continues until a confirmed file; Ctrl+C aborts like any other prompt.
- Resume text with several emails/phones, or a header like "Toronto, Ontario" (two parts): no proposal for the ambiguous fields.
- Resume file unreadable text encoding in a `.txt`: read tolerating bad bytes (replacement) for proposals; not a crash.

## Out of scope
- OCR for scanned PDFs.
- LLM-based reading or profile filling.
- Pre-filling skills, years of experience, education or target roles (and postal code).
- Changes to scoring, tailoring, cover letter stage, preflight checks, honest stage results, Playwright install, discovery timeouts.
- Changes to other doctor checks.

## Open questions
- Name used for the registry entry (proposed "Master resume") and whether a re-run refreshes the registered copy or only keeps the existing one. Proposed: keep the existing entry, and refresh its stored text if `resume.txt` changed.
- How "user-supplied" `resume.txt` is told apart from a PDF-extracted one (product expectation: extracted ones are replaced silently). Proposed: treat `resume.txt` as extracted only if `resume.pdf` exists and the file was written by init from it; otherwise ask.
- Whether the 200-character threshold applies before or after trimming whitespace (req assumes the extracted length as given).
