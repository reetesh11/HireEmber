---
class: bootstrap
size: medium
title: Add test harness and CI, block LinkedIn, extend doctor checks
---
# Requirements: Add test harness and CI, block LinkedIn, extend doctor checks

## Problem
The fork (HireEmber, package still `applypilot`) has no `tests/` folder, and `.github/workflows/ci.yml` runs only on `workflow_dispatch`, so later phases have nothing to build on. LinkedIn is in the default JobSpy site lists (`src/applypilot/discovery/jobspy.py` `search_jobs` and `_full_crawl`) and in `config/searches.example.yaml`, which goes against the no-LinkedIn policy. `applypilot doctor` does not check the Python version, the database or the configured sources. The README does not say this project is a fork.

## Requirements
- R1. The repository shall have a `tests/` pytest harness with a shared `tests/conftest.py`, and `pytest tests/` and `ruff check .` shall both pass.
- R2. When code is pushed or a pull request is opened, CI shall run `ruff check .` and the pytest suite on Python 3.11, 3.12 and 3.13, and shall fail if either one fails.
- R3. While default config is in use, the system shall not include `linkedin` in any JobSpy site list.
- R4. If discovery receives a job whose URL or application URL is on a LinkedIn host, then the system shall not store it in the `jobs` table.
- R5. If the apply stage is given a LinkedIn job URL, then the system shall reject it before any Chrome or Claude Code process starts.
- R6. When `doctor` runs, the system shall report Python version (3.11 or later), Chrome, Node (18 or later), Claude Code CLI, the database and the configured sources, each as present/OK or missing.
- R7. The test suite shall provide a local HTML fixture form (text inputs, a file upload, a submit button) that tests can load without network access.
- R8. The README shall state that the project is a fork of ApplyPilot under AGPL-3.0 and shall keep the upstream copyright and attribution.
- R9. The repository shall have a starter traceability file that maps FR-DIS-2, SAF-4, FR-CLI-2, NFR-1, NFR-10 and NFR-11 to the tests that cover them.

## Acceptance criteria
- AC-1: `tests/` exists with `tests/conftest.py`. `PYTHONPATH=src python3 -m pytest tests/` exits 0 and `ruff check .` exits 0 at the repo root. `pyproject.toml` dev extras include pytest and ruff.
- AC-2: `.github/workflows/ci.yml` has `push` and `pull_request` triggers. Its lint step runs `ruff check .` (not `ruff check src/`) and its test step runs pytest on `tests/`. A failing test or lint error fails the job, so there is no `continue-on-error` or `|| true`.
- AC-3: `search_jobs` and `_full_crawl` in `jobspy.py`, when called with `sites=None`, pass a `site_name` list to `scrape_jobs` that does not contain `linkedin`. A test stubs `scrape_jobs` and checks this. `src/applypilot/config/searches.example.yaml` does not list `linkedin` under `boards`.
- AC-4: Given discovery results that include rows with URLs such as `https://www.linkedin.com/jobs/view/123` and `https://linkedin.com/jobs/view/456`, plus one non-LinkedIn row, only the non-LinkedIn row is stored (tested via `store_jobspy_results` or the discovery store path, using a temporary SQLite DB).
- AC-5: Given a LinkedIn job URL as the apply target (e.g. `applypilot apply --url https://www.linkedin.com/jobs/view/123`, or a queued job whose `application_url` is LinkedIn), the apply stage rejects it with a message naming LinkedIn. A test confirms that the Chrome launch and Claude Code subprocess functions are never called.
- AC-6: `doctor` output contains a line for each of Python version, Chrome/Chromium, Node.js, Claude Code CLI, database and configured sources. A test with `CHROME_PATH` unset and Chrome hidden from discovery (`get_chrome_path` raising `FileNotFoundError`, or an empty `PATH`) shows Chrome/Chromium as MISSING. A test with Node below 18 or absent shows Node.js as MISSING.
- AC-7: A fixture HTML file under `tests/` (e.g. `tests/fixtures/forms/basic_form.html`) contains at least one `<input type="text">`, one `<input type="file">` and one submit button. A pytest fixture serves it from a local HTTP server on `127.0.0.1`. A test fetches it and finds those three elements, with no external network.
- AC-8: `README.md` has a section saying the project is a fork of ApplyPilot (with a link to the Pickle-Pixel/ApplyPilot repo), licensed AGPL-3.0, and keeps the existing upstream attribution and License section.
- AC-9: `docs/traceability.md` exists and has a table with rows for FR-DIS-2, SAF-4, FR-CLI-2, NFR-1, NFR-10 and NFR-11, each pointing to at least one test file or test name (NFR-1 may point to the doctor tests and CI matrix).

## Out of scope
- Data-model changes (phase 1), the package rename to HireEmber (phase 0b), CapSolver removal and any apply-stage rework beyond rejecting LinkedIn URLs (phase 3).
- Removing the `linkedin_url` profile field. It is the user's own profile link, not a job source.
- Running a browser against the fixture form. This phase only serves it, and browser tests come later.
- A macOS CI runner. NFR-1 is covered here by doctor checks and the Linux CI matrix.

## Assumptions
- A LinkedIn URL is any URL whose host is `linkedin.com` or a subdomain of it.
- An explicitly configured `linkedin` site (in user `searches.yaml` or a `sites` argument) is also removed, with a logged warning, because FR-DIS-2/SAF-4 say the system shall not read from LinkedIn at all, not only by default.
- "Database" in doctor means the SQLite DB path from `applypilot.config`: OK if it exists and opens, otherwise MISSING with a hint to run `init`. "Configured sources" means the JobSpy boards from the search config (after LinkedIn removal) plus the employer/site configs that load. Existing doctor checks (profile, resume, LLM key, CapSolver) stay.
- Tests live in `tests/` (acceptance tests in `tests/acceptance/` per standards). The fixture server uses the stdlib `http.server`, with no new runtime dependency.
- Ruff errors already in the code are fixed as part of this task so that `ruff check .` passes. The current lint state could not be checked here because ruff is not installed locally.

## Suggested split
(not needed)

## Open questions
- none
