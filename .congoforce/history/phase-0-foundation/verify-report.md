# Verify report — phase-0-foundation

## Result
PASS. All nine acceptance criteria are met and there are no blocking findings. There is one major robustness issue in the new doctor sources check.

Executable checks (from checks.md): lint passed, 70 tests passed with 0 failed, and the frozen set is intact. I did not re-run them.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | tests/ harness, pytest and ruff pass, dev extras | met | `tests/conftest.py` (frozen); `pyproject.toml` has `dev = ["pytest>=7.4", "ruff>=0.6"]`, `[tool.ruff.lint] select`, `[tool.pytest.ini_options]`; lint fixes in commit a00162b; checks.md shows lint and tests passing |
| AC-2 | CI on push/PR, `ruff check .`, pytest on tests/, no masking | met | `.github/workflows/ci.yml` triggers `push`/`pull_request`/`workflow_dispatch`, matrix 3.11/3.12/3.13, `ruff check .`, `python -m pytest tests/ -v` with `PYTHONPATH: src`, no `continue-on-error` or `|| true` |
| AC-3 | Default JobSpy site lists exclude linkedin; example yaml | met | `config.DEFAULT_JOBSPY_SITES`, and `resolve_jobspy_sites` is used in `jobspy.search_jobs` and `_full_crawl`; both `linkedin_fetch_description` branches are removed; `searches.example.yaml` boards has no linkedin; `test_ac3_jobspy_sites.py` |
| AC-4 | LinkedIn rows not stored | met | `store_jobspy_results` checks `job_url` and `job_url_direct` before insert; `database.store_jobs`, `workday.store_results` and `smartextract._store_jobs_filtered` also skip them, so all four `INSERT INTO jobs` paths are covered; `test_ac4_store_skips_linkedin.py` |
| AC-5 | Apply rejects LinkedIn before Chrome/Claude | met | `cli.apply` guard runs before `_bootstrap()` (cli.py:162-166); `launcher.main` and `gen_prompt` raise `LinkedInBlockedError` as their first statement; `worker_loop` marks the job failed/99 before `launch_chrome`; `test_ac5_apply_rejects_linkedin.py`, `tests/unit/test_apply_linkedin.py` |
| AC-6 | doctor lines for Python, Chrome, Node, Claude, DB, sources; MISSING cases | met | new `src/applypilot/doctor.py` has the 12 checks in the contract order; `cli.doctor` only renders them, one line each with `soft_wrap=True`; `test_ac6_doctor.py` (12 tests), `tests/unit/test_doctor.py` |
| AC-7 | Local fixture form served on 127.0.0.1 | met | `tests/fixtures/forms/basic_form.html` and the `fixture_form_server` fixture in conftest; `test_ac7_fixture_form.py` |
| AC-8 | README fork notice, AGPL-3.0, attribution kept | met | `## Fork notice` sits under the disclaimer and links Pickle-Pixel/ApplyPilot with AGPL-3.0; the `## License` section and the upstream badges and attribution are unchanged |
| AC-9 | docs/traceability.md table | met | the table header matches the contract; all six requirement IDs are present, each with test paths; NFR-1 and NFR-11 also name ci.yml; NFR-10 says it is completed in phase 6 |

## Spec compliance
- The code matches the tech.md tasks one-for-one. There are 7 implementation commits for 7 tasks, plus the spec commit.
- The implementer went slightly beyond the plan in two places, both harmless:
  - `cli.doctor` escapes Rich markup in names and notes (`rich.markup.escape`), so a path with `[` cannot break the rendering.
  - `is_linkedin_url` also accepts protocol-relative `//host` URLs and strips a trailing dot from the host. Both are reasonable hardening.
- Architecture: every component and edge in the diagram exists in the code (cli→doctor, cli→launcher, doctor→config, doctor→workday.load_employers, launcher→config with the gate before chrome/claude, jobspy→config, jobspy→scrape_jobs, database/workday/smartextract→jobs, ci→tests). The one undrawn edge is cli→config (`is_linkedin_url`), which tech.md task 5 itself specifies, so I recorded it as a note.
- Nothing missing that I could find. The out-of-scope items were left alone: the `linkedin_url` profile field, CapSolver, the package rename, and the `boards` versus `sites` key quirk.

## Code quality
- **Major, `src/applypilot/doctor.py:110-116`.** `check_sources` loads searches.yaml, employers.yaml and sites.yaml with no error handling. A malformed user `searches.yaml` now crashes `applypilot doctor` with a traceback. Before this change, doctor only checked that the file existed. A diagnostic command should report the broken config, for example as `Job sources MISSING <error>`, rather than crash. The fix is small: wrap the loads in try/except and return a MISSING Check.
- **Note, `src/applypilot/config.py:183`.** `resolve_jobspy_sites` iterates a scalar string such as `sites: indeed` character by character. This problem existed before the change; the fix would be a one-line normalisation.
- **Note, `src/applypilot/discovery/workday.py:317`.** Only the resolved URL is checked here, while the other store paths also check `application_url`. This is consistent with the contract.
- **Note.** The `.congoforce/history/...` and `.congoforce/standards.md` files are committed by the pipeline's spec commit and will land on main.
- I checked the worker_loop rejection path (launcher.py:604-612). The rejected job is marked `failed` with `apply_attempts=99`, so `acquire_job` will not pick it up again and queue mode cannot loop forever. It is not counted in `jobs_done`, which matches the contract.
- Lint-fix commit: I checked each removed import and variable. All were unused, and none of the removed assignments had side effects (`auth_info`, `projects`/`projects_str` and `exc` were plain `.get`/binding). No other module re-imported the removed names.

## Recommendation
Ready for a human reviewer. Before merge, I suggest hardening `doctor.check_sources` against malformed YAML (the major finding). It is not blocking.
