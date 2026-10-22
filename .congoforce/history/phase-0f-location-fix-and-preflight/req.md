---
class: feature
size: large
title: Fix location matching and add a settings check before run and apply
---
# Requirements — Fix location matching and add a settings check before run and apply

## Problem
Two issues. (1) The phase 0e location filter skips jobs such as "Calgary, AB" for a user whose only target is "Canada", because the text names no country. It should skip only text that is recognisably somewhere else. (2) `hireember run` and `hireember apply` fail late and in different ways when settings are missing (a model tier, a registered resume, `resume.txt`, the browser, jobspy). The user wants one check at the start that lists everything missing and offers to fix it.

## Requirements

### Location
- R1. When a job's location text contains a region (Canadian province or territory, US state or DC), the system shall treat the region as belonging to its country; a country target (profile `country` or an accept entry naming a country) shall accept every region of that country, and a region target (for example "Alberta") shall accept that region only.
- R2. When the location text contains no recognised region or country token (for example "Calgary", "Greater Toronto Area"), the system shall not skip the job. Remote, empty, placeholder and no-target behaviour shall stay as in phase 0e.
- R3. When a bare two-letter code is both a country and a region (`CA`), the system shall pass the job if either meaning fits the targets.
- R4. When a job is skipped for location, the skip reason shall keep the form `location: <text>`.

### Settings check
- R5. When `hireember run` or `hireember apply` starts, the system shall first check what the requested stages need, before any work:
  - `discover`: a search config, and python-jobspy importable when a job board source is configured.
  - `enrich`: the Playwright browser, when smart extract or enrichment will run.
  - `score`, `tailor`, `cover`: the fast tier (score), the quality tier (tailor, cover), a registered base resume with a text file, and a profile.
  - `apply`: profile, Claude Code CLI, Chrome, tailored resumes available.
- R6. When `--dry-run` or an `apply` utility mode (`--mark-applied`, `--mark-failed`, `--reset-failed`) is used, the system shall skip the check.
- R7. The system shall list everything missing in one plain-words message, each item with its exact fix, and shall not stop at the first problem.
- R8. While running in an interactive terminal, the system shall offer to fix, one at a time, each missing item that can be set inside HireEmber:
  - missing model tier: ask provider, model, base URL (custom) and API key (non-local) as `init` does, and save with the same code as `models set`; for the quality tier also offer "use the same settings as the fast tier".
  - missing resume: ask for the file path, extract and register as `init` does.
  - missing browser: offer to run `playwright install chromium`.
  - missing profile or search config: offer to run the matching `init` step.
- R9. Items needing an outside install (Claude Code CLI, Chrome, jobspy in the wrong Python) shall be shown with their command and not prompted.
- R10. If the user declines the only thing a stage needs, then the system shall stop with exit code 1 and the list of what is missing. If the user declines something only an optional stage needs, the system shall run the other stages and say which were skipped.
- R11. If there is no interactive terminal, or `--no-prompt` is given, then the system shall not prompt or wait, shall print the missing list, and shall exit 1 before any stage starts.
- R12. After each fix the system shall re-evaluate, then continue the run without a restart.
- R13. The check shall reuse the logic behind `hireember doctor`, and shall make no LLM call (a reachability probe of at most a few seconds per tier is allowed).
- R14. The system shall never echo answers (API keys) and shall not guess values.

## Acceptance criteria
- AC-1: `pytest` and `ruff check .` pass.
- AC-2: With the only target "Canada", "Calgary, AB", "Toronto, ON", "Vancouver, British Columbia" and "Montreal, QC, Canada" are not skipped; "Austin, TX" and "London, UK" are skipped with reason `location: <text>`.
- AC-3: With the target "Alberta" (no country), "Calgary, AB" is not skipped and "Toronto, ON" is skipped.
- AC-4: "Calgary" and "Greater Toronto Area" are not skipped. A bare `CA` passes when the targets are Canada, and also when they are California.
- AC-5: Remote, empty, placeholder and no-target cases behave as in phase 0e (phase 0e tests that expected a skip for text with no recognised region are updated per R2).
- AC-6: With the quality tier unconfigured, `hireember run tailor` in a terminal reports it, prompts, saves the answers to `models.toml`, and proceeds without a restart.
- AC-7: With the quality tier, registered resume and browser all missing, one message lists all three, then prompts item by item.
- AC-8: Without a terminal, or with `--no-prompt`, nothing is prompted, the list is printed, the exit code is 1 and no stage starts.
- AC-9: Declining the only required item exits 1; declining an optional stage's item lets the other stages run and names the skipped ones.
- AC-10: `run discover` does not ask about models; `run score` asks for the fast tier only; `run tailor cover` asks for the quality tier.
- AC-11: `apply` lists a missing Claude Code CLI or Chrome with its install pointer and does not prompt for them.
- AC-12: `--dry-run` and the `apply` utility modes skip the check.
- AC-13: API key values never appear in output.
- AC-14: Stages, gating, queue, wizard steps, `doctor` and `models` behave as before; no LLM call is made by the check.

## Out of scope
- Region data for countries other than Canada and the United States.
- New dependencies.
- Changing `doctor` or `models` output or behaviour.
- Installing Claude Code CLI, Chrome or jobspy on the user's behalf.

## Assumptions
- Region-to-country data is a small built-in table (Canada and US only); other countries keep phase 0e matching.
- Existing phase 0e location tests conflicting with R2 are updated, not frozen.
- "Interactive terminal" means stdin and stdout are both TTYs.

## Suggested split
Sized large because the location fix and the settings check are independent deliverables; the second also spans `run`, `apply`, `doctor`, `models` and `init`. If the human prefers one loop, approve as is.
1. Location matching fix (R1-R4; AC-2 to AC-5). Small.
2. Settings check core: detection of needs per stage, one-message list, `--no-prompt`/non-TTY exit 1, dry-run skip (R5-R7, R9, R11, R13, R14; AC-8, AC-10 to AC-13).
3. Interactive fixes: model tiers, resume, browser, profile/search config, decline handling, re-evaluate (R8, R10, R12; AC-6, AC-7, AC-9).

## Open questions
- Keep this as one task, or split into the three requirements above?
- When the user accepts "use the same settings as the fast tier", should the API key be copied into the quality tier's stored config, or referenced from the fast tier?
