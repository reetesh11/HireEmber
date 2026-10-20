# Product spec — Add fast/quality model tiers, location pre-skip and one-command install

Shipped as one PR (gate 1 answer). Product name in user-facing copy is `hireember`.

## User-facing behaviour

### 1. Model tiers

**Tiers.** The user has two model tiers.
- `fast`: scoring a job, choosing or classifying a resume, discovery and enrichment extraction.
- `quality`: resume tailoring and cover letters.

Each tier has: provider preset or custom endpoint, model name, base URL, optional API key. Presets: `gemini`, `openai`. Any other OpenAI-compatible endpoint (for example Ollama at `http://localhost:11434/v1`) is a custom base URL. A tier whose base URL is local (localhost or 127.0.0.1) needs no key.

**Config file.** One file in the data folder holds both tiers. It is plain TOML, `models.toml`. The file is written by `hireember init` (AI step) and `hireember models set`. The user can edit it by hand. An API key may be stored in it or supplied by environment variable. The file is created with owner-only permissions where the OS allows.

**Resolution order per tier** (first match wins):
1. That tier's section in the config file.
2. The legacy settings: `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LLM_URL` + `LLM_MODEL`, from `.env` or the environment.

Consequences:
- Only legacy env set: both tiers use that one provider and model, same as today.
- Only one tier in the file: the other tier uses the legacy settings.
- Nothing configured for a tier: the tier is "unconfigured" (see errors).

**`hireember models show`**
Prints one block per tier, never an API key value (only `key: set` or `key: not set`, or `key: not needed (local)`). Also shows the source of each value (`config file` or `environment`).

```
Model tiers

fast
  provider: gemini
  model:    gemini-2.0-flash
  base url: (preset)
  key:      set (environment)
  source:   environment

quality
  provider: custom
  model:    llama3.1:70b
  base url: http://localhost:11434/v1
  key:      not needed (local)
  source:   config file
```

**`hireember models set fast|quality [options]`**
Options: `--provider gemini|openai|custom`, `--model NAME`, `--base-url URL`, `--api-key KEY`. Only the options given change; other stored values stay. Prints `Saved fast tier to <path>.` The key value is never echoed. A tier name other than `fast` or `quality` prints `Tier must be 'fast' or 'quality'.` and exits non-zero. Running `set` with no options prints `Nothing to change. Pass --provider, --model, --base-url or --api-key.` and exits non-zero.

**`hireember models test`**
Makes one tiny call per tier, in order fast then quality. One line per tier:
```
fast     ok       gemini-2.0-flash (0.8s)
quality  FAILED   Cannot reach http://localhost:11434/v1. Is Ollama running?
```
If both tiers resolve to the same provider and model, both lines still print. Exit code 0 when all tiers ok, 1 otherwise.

**`hireember init` AI step.** Asks for the fast tier (provider, model, URL, key as needed). Then asks "Use a different model for tailoring and cover letters? [y/N]". On N, only the fast tier is stored and quality follows the fallback in the resolution order (legacy settings) and `init` says so. On Y, asks the same questions for quality. Writes the same `models.toml` that `models set` writes. Existing non-AI wizard steps are unchanged.

**`hireember doctor`.** One line per tier replaces the single LLM line, showing provider, model and reachability:
```
LLM fast     OK       gemini / gemini-2.0-flash, reachable
LLM quality  WARN     ollama / llama3.1:70b, not reachable: Cannot reach http://localhost:11434/v1
```
Unconfigured: `LLM fast  MISSING  not configured — run 'hireember models set fast' or 'hireember init'`.

**Run summary.** `hireember run` ends with a line per stage showing the model used, for example `scoring: gemini-2.0-flash (fast)` and `tailoring: llama3.1:70b (quality)`. A stage that did not run is not listed.

### 2. Location pre-skip

Before the LLM scores a job, a deterministic check compares the job's location with the user's targets:
- Accept entries and reject entries from the `locations` / `location` settings.
- Profile city, province/state and country.
- Whether remote is accepted.

Decision:
- Location empty or blank, or not recognisable: not skipped, scoring continues.
- Remote job and the user accepts remote: not skipped.
- Location matches any accept entry, or the profile province/state or country: not skipped. A recognised city in the user's province or country that is not in the accept list is kept (gate 1 answer).
- Location recognised and matches no accept entry, province or country: skipped. If the location matches a reject entry it is also skipped.
- Matching is case-insensitive and ignores punctuation, so `Toronto, ON, Canada` matches accept entry `toronto`.
- If a job lists several locations, it is skipped only when none of them passes.

Skipped job: ticket status `skipped`, status reason exactly `location: <job location as stored>` (for example `location: Berlin, Germany`). No LLM call is made. The reason shows in the ticket history (`hireember ticket log <id>`) and in `hireember status`, which gains a row `Skipped by location` with the count. The check applies to jobs from jobspy, Workday and smart extract, at scoring time.

**Scoring prompt.** Contains an instruction that a job whose location is incompatible with the candidate's target locations is a reason for a low score.

### 3. One-command install

- `pip install -e .` (and `pip install hireember`) installs `python-jobspy` and its dependencies, including `curl_cffi`. No `--no-deps` step anywhere in the docs.
- `hireember doctor` jobspy line: `python-jobspy  OK  Job board scraping available`. If import fails: `python-jobspy  WARN  Not importable. Reinstall hireember in the active Python: <sys.executable> -m pip install -e .` (the actual interpreter path is shown).
- The README install section drops the `--no-deps` instructions and the separate package list.
- Playwright Chromium: `doctor` shows `Playwright Chromium  MISSING  Run: playwright install chromium` when the browser is absent, and `OK` with its path when present.
- `hireember init` offers: `Playwright Chromium is not installed. Run 'playwright install chromium' now? [Y/n]`. Y runs the command, streams its output and reports `Installed.` or a one-line failure plus the manual command. N prints the command and continues. No prompt when already installed.

## Acceptance criteria

- AC-1: `pytest` and `ruff check .` exit 0.
- AC-2: With only `GEMINI_API_KEY` set (no config file), resolving `fast` and `quality` returns the same provider (`gemini`), model and key as today's single client.
- AC-3: With distinct `fast` and `quality` settings, a fake client records tier `fast` for scoring (and resume choice, extraction) and tier `quality` for tailoring and cover letter calls. Every LLM call site requests a tier by name; none uses an unnamed default.
- AC-4: A tier with a local base URL and no API key resolves without error. `hireember models test` prints one result line per tier (`ok` or `FAILED` with a one-line reason).
- AC-5: `hireember models show` prints both tiers and no API key text appears in its output, even when a key is set in the file or env. `models set` changes the stored value (a following `show` reflects it and other fields stay). `init` writes the same `models.toml`.
- AC-6: With an unreachable or unconfigured tier, `models test` and `doctor` each print a one-line plain message for that tier and no traceback; `models test` exits 1.
- AC-7: A job whose location is recognised and matches no accept entry, province or country gets status `skipped`, reason `location: <text>`, and a fake client records zero calls.
- AC-8: Not skipped by the check: remote jobs when remote is accepted, empty or blank locations, unrecognisable locations, and a recognised city in the user's province or country that is not in the accept list.
- AC-9: The check runs, with the skip outcome of AC-7, for a job from each of jobspy, Workday and smart extract.
- AC-10: `pyproject.toml` lists `python-jobspy` as a plain dependency (no extra, no `--no-deps` note). `import jobspy` works in an environment created by `pip install -e .` alone.
- AC-11: `doctor` output never contains `--no-deps`. When Chromium is missing it contains `playwright install chromium`.
- AC-12: The scoring prompt text contains the sentence that an incompatible location is a reason for a low score.
- AC-13: The skip reason `location: <text>` appears in `hireember ticket log <id>` and the count appears in `hireember status`. (req.md says `ticket list`; no such command exists, see open questions.)
- AC-14: Apply, gates, queue and non-AI wizard steps behave as before; all pre-existing tests still pass.

Added from implied behaviour:
- AC-15: `models set` with an invalid tier name or no options prints the messages above and exits non-zero without changing the file.
- AC-16: With only one tier in `models.toml`, the other tier resolves from legacy env settings (R4); with neither, `show` marks it `not configured`.
- AC-17: The run summary lists the model used per stage (R5).
- AC-18: `hireember init` offers the Chromium install only when it is missing, and declining does not abort init.

## Edge cases and errors

- Missing key for a non-local tier: `fast tier has no API key. Set it with 'hireember models set fast --api-key ...' or the GEMINI_API_KEY / OPENAI_API_KEY variable.`
- Unreachable URL, timeout, 401/403, unknown model: each becomes one plain line (for example `Cannot reach <url>`, `Key rejected by <provider>`, `Model '<name>' not found`). No traceback, no raw exception class.
- Malformed `models.toml`: `models show/test/set` and `doctor` print `models.toml is not valid TOML (line N). Fix or delete it: <path>` and do not overwrite the file.
- Config file and env both set a value for a tier: the file wins; `show` reports the source.
- `models test` costs a few tokens per tier; it is not run automatically except by `doctor` reachability checks, which must not generate text (a lightweight reachability probe is enough).
- Location with variants (`Remote - US`, `Hybrid, Toronto`): remote wording passes when remote is accepted; otherwise the non-remote part is checked.
- Remote job when the user does not accept remote: location check applies to any stated place, empty remote location is not skipped.
- Job already scored or with an existing ticket is not re-skipped retroactively.
- `curl_cffi` unavailable for the user's Python/platform at install: pip fails with its own error; no hireember-specific handling.
- `playwright install chromium` fails (offline): one-line failure, manual command shown, init continues.

## Out of scope

- New LLM providers beyond OpenAI-compatible endpoints and the Gemini/OpenAI presets.
- Using an LLM for the location check.
- Installing Playwright browsers via pip.
- Re-checking location for jobs already scored.

## Open questions

- req.md refers to `hireember ticket list`, which does not exist (only `ticket log <id>` and `status`). Spec assumes the reason shows in `ticket log` and `status`. Should a `ticket list` command be added?
- Config file name and format: spec assumes `models.toml` in the data folder. Acceptable, or should it be the generic `config` file named in input.md?
- Should the `status` row `Skipped by location` be added, or is the reason in ticket history enough?
- req.md front matter says size large; the task is labelled medium. No spec impact.
