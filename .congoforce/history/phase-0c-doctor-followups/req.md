---
class: bug
size: small
title: Harden doctor source checks and fix config and docs follow-ups from phase 0b
---
# Requirements — Harden doctor source checks and fix config and docs follow-ups from phase 0b

## Problem
`hireember doctor` (`doctor.check_sources`) still raises when a config file has a nested value of the wrong type, although it promises never to raise. A string `sites:` value can also be split into letters. Three small issues remain: `resolve_app_dir` treats a stray `~/.hireember` file as the data folder, the README PyPI badge points at the old `applypilot` package, and CONTRIBUTING shows a `hireember discover` command that does not exist.

## Requirements
- R1. If `sites` in `searches.yaml` is not a list of strings, `employers` in `employers.yaml` is not a mapping, or `sites` in `sites.yaml` is not a list, then `check_sources` shall return `Check("Job sources", "MISSING", "<file>: <what is wrong>")` and shall not raise.
- R2. If a `sites:` value is a single string (for example `indeed`), then `check_sources` shall report MISSING with a note that it must be a list, and shall not split it into letters.
- R3. If `config.resolve_jobspy_sites` receives a non-list, non-None value, then it shall raise `ValueError` with a message saying a list is required, and shall not iterate a string by character. Discovery callers shall report that error instead of crashing.
- R4. When resolving the data folder, `resolve_app_dir` shall choose `~/.hireember` only if it is a directory.
- R5. The README PyPI badge shall link to `https://pypi.org/project/hireember/`.
- R6. CONTRIBUTING shall show only commands that exist, replacing the two `hireember discover --employer/--site` examples (lines 48 and 69) with the real discovery command (`hireember run discover`, or what `hireember run --help` shows).

## Acceptance criteria
- AC-1: `pytest` and `ruff check .` pass.
- AC-2 (reproduce, fails today): For each of `sites: 5`, `sites: indeed` and `sites: {a: 1}` in `searches.yaml`, `check_sources()` returns status MISSING with a note naming `searches.yaml`. It raises nothing, and the note never lists single letters.
- AC-3: `employers: 5` in `employers.yaml` and `sites: 5` in `sites.yaml` each give MISSING with a note naming the file. A `sites:` string in `sites.yaml` also gives MISSING with a "must be a list" note.
- AC-4: `resolve_jobspy_sites("indeed")` raises `ValueError` whose message mentions a list. A discovery caller given such a value reports the error without an unhandled exception.
- AC-5: With a home folder holding a file named `.hireember` and a directory `.applypilot`, `resolve_app_dir(home=...)` returns `(<home>/.applypilot, True)` and the legacy notice is printed.
- AC-6: The README badge links to `pypi.org/project/hireember`. CONTRIBUTING has no `hireember discover` string, and every `hireember` command shown there exists in `hireember --help` or a subcommand's help.
- AC-7 (unchanged behaviour): `resolve_jobspy_sites(None)` returns the defaults, and list input (with "linkedin" removed and a warning) behaves as before. Valid configs still give the same `check_sources` result. `resolve_app_dir` still honours `HIREEMBER_DIR`, uses an existing `~/.hireember` directory, and returns `~/.hireember` when neither folder exists.

## Out of scope
- Other doctor checks, the data model, and the apply stage.

## Assumptions
- Non-string items inside a `searches.yaml` `sites` list count as "not a list of strings".
- The README badge image URL (`img.shields.io/pypi/v/...`) should also use `hireember`.
- "Discovery callers" means the code paths that call `resolve_jobspy_sites`; each reports the `ValueError` message and exits or skips cleanly.

## Open questions
- none
