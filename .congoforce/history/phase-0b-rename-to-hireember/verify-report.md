# Verify report — phase-0b-rename-to-hireember

## Result
PASS. All 12 acceptance criteria (AC-1 to AC-11, plus AC-12 added at gate 1) are met and there are no blocking findings. One major non-blocking finding is about doctor's robustness against bad YAML.

## Acceptance criteria
| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| AC-1 | pytest and ruff exit 0 | met | checks.md: lint pass, 135 passed / 0 failed; frozen set intact |
| AC-2 | `src/hireember` exists, `src/applypilot` gone, `__version__` non-empty | met | `ls src` shows only `hireember`; `src/hireember/__init__.py:3`; tests/acceptance/test_hireember_ac2_package.py |
| AC-3 | no `import/from applypilot` in src or tests | met | `grep -rni applypilot src` hits only the legacy constants in config.py:17-30; test_hireember_ac3_no_legacy_imports.py |
| AC-4 | `--help` lists exactly the 6 commands; `--version` prints `hireember 0.3.0` | met | cli.py:21 `name="hireember"`, cli.py:230 version callback; `__main__.py` imports `hireember.cli`; test_hireember_ac4_cli.py checks the exact command set, `-V`, and `python -m hireember` |
| AC-5 | pyproject name, single script, wheel packages and artifacts | met | pyproject.toml:2, :35, :47, :50; urls and authors unchanged |
| AC-6 | `HIREEMBER_DIR` wins, no notice | met | config.py:439-441 (strip + expanduser, so an empty value counts as unset); test_hireember_ac6_app_dir_env.py |
| AC-7 | empty HOME gives `~/.hireember`, no notice | met | config.py:448; test_hireember_ac7_app_dir_default.py; `APPLYPILOT_DIR` is never read |
| AC-8 | legacy-only HOME uses `~/.applypilot` with one stderr notice and touches nothing | met | config.py:445-453 (`is_dir`, `sys.stderr.write` once at import), DB stays `applypilot.db` (config.py:457); test_hireember_ac8_legacy_app_dir.py snapshots the folder and checks that stdout is clean |
| AC-9 | both folders present gives `.hireember`, no notice | met | config.py:442-444; test_hireember_ac9_both_dirs.py |
| AC-10 | the AC-10 grep is clean outside the legacy code | met | the grep matches only config.py:21-22 (notice) and :30 (resolver docstring) |
| AC-11 | README uses hireember and keeps attribution; LICENSE unchanged | met | README title `# HireEmber`, every command example is renamed, the line-3 disclaimer and fork notice are untouched, the License section credits upstream ApplyPilot; the diff for LICENSE is empty |
| AC-12 (gate 1) | doctor survives malformed searches/employers/sites YAML | met | doctor.py:109-158 (`_load_yaml_mapping`, `_bad_source`, try/except around each source, check for a non-dict `search_cfg`); test_hireember_ac12_doctor_bad_yaml.py, tests/unit/test_doctor_sources.py |

## Spec compliance
- Every tech.md task is implemented as specified: the `git mv` (history follows), the four-step `resolve_app_dir`, the DB file name split from gate-1 answer 1, `APPLYPILOT_DIR` dropped per gate-1 answer 2, the notice going to plain stderr, the doctor LLM note using `config.ENV_PATH`, and doctor no longer importing `workday.load_employers`.
- There are five commits, one per tech.md task, after the freeze commit. Commit 1 includes the conftest/harness edits as answers.md instructs.
- `tests/conftest.py` was changed to `HIREEMBER_DIR`, as the Assumptions section and the gate-2 freeze require. The helper confirmed that the frozen hashes match.
- The CHANGELOG `[Unreleased]` entry covers the rename, the env var, the default folder and DB name, the legacy fallback with the move command, and the doctor fix.
- Nothing was built beyond the spec. Text that credits upstream (README line 3, fork notice, the "vs The Alternatives" table, `[project.urls]`, `authors`) is kept as tech.md says.

## Code quality
- **major** `src/hireember/doctor.py:145`, `:161`: `check_sources` still raises `TypeError` on a wrongly-typed nested value. Examples: `sites: 5` in searches.yaml (raised inside `config.resolve_jobspy_sites`, config.py:221), or `employers: 5` / `sites: 5` in the shipped registries (raised at `len()`). `sites: indeed` as a string is split into characters and reported OK ("JobSpy: i, n, d, e, e, d"). I confirmed both by calling `check_sources` directly. This is not a regression, because the old code behaved the same way, and the gate-1 request only named parse errors and non-mapping top levels. It does contradict the new docstring at doctor.py:131 ("never raises") and the contract line "never raises on bad config". This should be a follow-up.
- **note** `README.md:13`: the PyPI badge still points at the `applypilot` package. It was kept on purpose per tech.md.
- **note** `CONTRIBUTING.md:48`, `:69`: `hireember discover …` is not an existing subcommand. The text was inherited from upstream and renamed mechanically as instructed.
- **note** `src/hireember/config.py:443`: `current.exists()` lets a *file* named `~/.hireember` take precedence over a legacy directory. This matches the contract, but `.is_dir()` would be consistent with the legacy check.
- The rest is clean. The resolver is pure and small. The module-level constants keep every `from hireember.config import X` call site working. `_load_yaml_mapping` and `_bad_source` remove what would otherwise be three copies of the same handling. Error text is collapsed to one line. No stray `applypilot` strings remain in user-facing code.

## Recommendation
Ready for a human reviewer. Consider a small follow-up so `check_sources` validates the types of the nested `sites` and `employers` values, which would make "never raises" true for every malformed config.
