---
class: feature
size: large
title: Add fast/quality model tiers, location pre-skip and one-command install
---
# Requirements — Add fast/quality model tiers, location pre-skip and one-command install

## Problem
Every LLM call uses one client and one model, so cheap work (scoring, extraction) and expensive work (tailoring, cover letters) cost the same or the tailoring is weak. Jobs from jobspy, and every job at scoring time, are not location-checked, so out-of-area jobs get scored, tailored and queued. Installing needs extra steps for `python-jobspy`, and the `doctor` hint for it is stale.

## Requirements
Model tiers
- R1. The system shall provide two tiers: fast (scoring, resume choice/classification, discovery and enrichment extraction) and quality (resume tailoring, cover letters).
- R2. Each tier shall have its own model name, base URL and optional API key; Gemini and OpenAI shall remain available as presets and a local OpenAI-compatible server (Ollama) shall work without a key.
- R3. The system shall store both tiers in one config file in the data folder, written by `hireember init` (AI step) and by the new `hireember models` command (`show`, `set fast|quality ...`, `test`); `.env` variables shall keep working.
- R4. While only the legacy env variables are set, the system shall use that one model for both tiers; while only one tier is configured, the other tier shall use the legacy/shared settings.
- R5. Every LLM call site shall request a tier by name; `hireember doctor` shall show provider, model and reachability per tier, and the run summary shall show which model did what.
- R6. When `hireember models test` runs, the system shall make one small call per tier and report ok or a plain-language one-line error.
- R7. If a tier is unreachable or unconfigured, then `models test` and `doctor` shall print a one-line message and no traceback.

Location skip
- R8. Before the LLM scores a job, the system shall compare the job location to the target locations (`locations`/`location` accept and reject settings, plus profile city, province, country) and, when clearly outside them and not an accepted remote job, mark the job `skipped` with reason `location: <job location>` without calling the LLM.
- R9. If the job location is empty or unrecognisable, then the system shall not skip it and scoring shall continue.
- R10. The check shall apply to jobs from jobspy, Workday and smart extract.
- R11. Where the user accepts remote, remote jobs shall pass; the skip reason shall be visible in `hireember ticket list` / status.
- R12. The scoring prompt shall state that an incompatible location is a reason for a low score.

One-command install
- R13. `pip install -e .` shall install `python-jobspy` and its dependencies (including `curl_cffi`) as plain dependencies, with no `--no-deps` step.
- R14. `hireember doctor` shall report jobspy as OK, or tell the user to reinstall hireember in the active Python naming the interpreter; the stale hint in `doctor.py` and the README shall be removed.
- R15. If the Playwright Chromium browser is missing, then `doctor` shall print `playwright install chromium` and `hireember init` shall offer to run it.

## Acceptance criteria
- AC-1: `pytest` and `ruff check .` pass.
- AC-2: With only `GEMINI_API_KEY` set, fast and quality resolve to the same provider and model as today.
- AC-3: With distinct fast and quality settings, scoring uses the fast client and tailoring and cover letter use the quality client (fake client records the tier).
- AC-4: A tier with a local base URL and no API key resolves without error; `hireember models test` reports a result for each tier.
- AC-5: `hireember models show` prints both tiers and never prints an API key value; `models set` changes the stored value; `init` writes the same file.
- AC-6: An unreachable or unconfigured tier yields a one-line plain message from `models test` and `doctor`, with no traceback.
- AC-7: A job located outside target locations is marked `skipped` with reason `location: <text>` and a fake client records zero calls.
- AC-8: Remote (when accepted), empty and unrecognisable locations are not skipped by the check.
- AC-9: The check runs for a job from each of jobspy, Workday and smart extract.
- AC-10: `pyproject.toml` lists `python-jobspy` as a plain dependency; `import jobspy` works after `pip install -e .` alone.
- AC-11: `doctor` no longer prints the `--no-deps` hint; it mentions `playwright install chromium` when the browser is missing.
- AC-12: The scoring prompt contains the location-incompatibility instruction.
- AC-13: The skip reason appears in `ticket list`/status output.
- AC-14: Apply, gates, queue and non-AI wizard steps behave as before (existing tests still pass).

## Out of scope
- New LLM providers beyond OpenAI-compatible endpoints and the existing Gemini/OpenAI presets.
- Using an LLM for the location check.
- Installing Playwright browsers via pip.

## Assumptions
- The tier config is plain TOML or YAML in the data folder; keys may also come from the environment.
- The location check is deterministic code.
- "Clearly outside" is a conservative match: only skip when the location is recognised and matches none of the targets.

## Suggested split
1. Model tiers: config file, tier resolution, call-site tier names, `models` command, doctor/run summary (R1-R7).
2. Location pre-skip: code check at scoring time for all sources, skip reason, prompt line (R8-R12).
3. One-command install: jobspy dependency, doctor/README hint, Playwright check and init offer (R13-R15).

## Open questions
- Should the three parts ship as three separate PRs (as suggested), or as one?
- Is a recognised-but-unlisted city in the same province/country "clearly outside"? (Assumed yes unless it matches an accept entry, province or country.)
