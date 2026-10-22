# Product spec — Fix location matching and add a settings check before run and apply

Decisions from `answers.md` apply: one PR for both parts; "use the same settings as the fast tier" copies the values (provider, model, base URL, API key) into the quality tier's entry in `models.toml`; it does not reference the fast tier.

## User-facing behaviour

### Part A. Location matching

Nothing new is shown to the user. The only visible change is which jobs get status `skipped` with reason `location: <text>` before scoring (the same reason form phase 0e wrote, counted by `hireember status` as before).

How a job's location text is judged:

1. Each region found in the text (Canadian province/territory, US state, DC, by abbreviation or full name, as in the phase 0e table) is understood to belong to its country: Canada or the United States.
2. A country target (profile `country`, or any accept entry that names a country) accepts the country and every region of it. Target "Canada" accepts "Calgary, AB", "Toronto, ON", "Vancouver, British Columbia", "Montreal, QC, Canada".
3. A region target (for example "Alberta", or profile `province_state`) accepts that region only. Target "Alberta" accepts "Calgary, AB" and skips "Toronto, ON".
4. Text with no recognised region or country (for example "Calgary", "Greater Toronto Area") is never skipped, because the system cannot tell it is somewhere else.
5. Text with a recognised region or country that fits no target is skipped: "Austin, TX" and "London, UK" with target "Canada".
6. A bare `CA` counts as Canada and as California. The job passes if either fits the targets.
7. Remote wording, empty text, placeholders ("N/A", "TBD", "Various", "Worldwide" and so on), the no-target case, multi-part text split on `;` and `|` (job passes if any part passes), and reject patterns all behave as in phase 0e.
8. Other countries (for example "UK") stay as phase 0e: matched as tokens, recognised as "somewhere else" when they fit no target.

### Part B. Settings check at the start of `hireember run` and `hireember apply`

**When it runs.** First thing, after argument validation, before any stage starts and before any work or database writes done by stages. It looks only at what the requested stages need (`run` with no stages means `all`).

**When it is skipped.** `run --dry-run`; `apply --dry-run`; `apply --mark-applied`, `--mark-failed`, `--reset-failed`. Also skipped: `apply --gen` keeps its existing behaviour (needs listed under `apply` below still apply; the "tailored resumes available" need is not checked when `--gen --url` is used, as today).

**What each stage needs** (the check gives one item per missing need):

| Stage | Needs | Fix offered in terminal |
|---|---|---|
| discover | search config; python-jobspy importable when a job board source is configured | search config: run the `init` search step. jobspy: command shown only |
| enrich | Playwright Chromium, when smart extract or enrichment will run | offer to run `playwright install chromium` |
| score | fast tier configured; registered base resume with its text file; profile | model prompts; resume prompt; `init` profile step |
| tailor, cover | quality tier configured; registered base resume with text file; profile | same |
| apply | profile; Claude Code CLI; Chrome; tailored resumes available | profile: `init` step. Claude Code CLI and Chrome: command shown only. Tailored resumes: pointer to `hireember run score tailor`, not prompted |

`pdf` needs nothing extra beyond what its inputs need (unchanged).

**The message.** When anything is missing, one message is printed, in plain words, listing every missing item, each with its exact fix. It does not stop at the first problem. Shape:

```
Before this run can start, 3 things need setting up:

  1. Quality model (used by tailor, cover) is not set up.
     Fix: hireember models set quality
  2. No base resume is registered, or its text file is missing.
     Fix: hireember resume add <file> --name <name>
  3. Playwright browser is not installed (used by enrich).
     Fix: playwright install chromium
```

Each item names the stage(s) that need it. Fix lines reuse the same fix text `doctor` shows (`hireember models set <tier>`, `Run: playwright install chromium`, install pointers such as `https://claude.ai/code`, and for jobspy the line `<python> -m pip install -e .`). Exact wording of the sentences is for implementation; the item count, the stage names, and the fix commands are fixed.

**Interactive terminal** (stdin and stdout both TTYs, no `--no-prompt`). After the list, the system goes through the fixable items one at a time, in the order listed. Each starts with a yes/no offer (default yes), for example `Set up the quality model now? [Y/n]`.

- **Model tier.** Asks, in the order `init` asks: provider (gemini, openai, custom), model, base URL (custom only), API key (not asked for a local endpoint). The API key is typed hidden and never shown. Saved through the same code as `hireember models set`, so `models.toml` ends up identical to what `models set` would write. For the quality tier, the first question is `Use the same settings as the fast tier? [Y/n]`; yes copies the fast tier's provider, model, base URL and API key into the quality entry in `models.toml` and asks nothing more; no goes to the full questions. This choice is offered only when the fast tier is configured.
- **Resume.** Asks for the file path, extracts and registers as `init` does (same PDF extraction, confirmation and name handling as the `init` resume step).
- **Browser.** `Install the Playwright browser now (playwright install chromium)? [Y/n]`; yes runs that command and shows its progress output.
- **Profile / search config.** `Run the profile step of init now? [Y/n]` (likewise for search config); yes runs that `init` step only, not the whole wizard.
- **Install-only items** (Claude Code CLI, Chrome, jobspy in the wrong Python, tailored resumes for apply): stay in the list with their command; no prompt.

**After each fix** the system re-checks. An item that is now satisfied is confirmed with one line (`Quality model: set.`); if it is still not satisfied (wrong path, failed install, unreachable tier), the problem is shown and the user is offered the same fix again once more, or can decline. After the last item, the system prints a short line such as `All set. Starting run.` and the run starts in the same process.

**Declining.**
- Declining any prompt leaves that item missing.
- If a stage's required need stays missing and that stage is the only one requested (or the only thing remaining to do), the run stops with exit code 1 and prints the list of what is still missing.
- If the missing item belongs only to a stage that is optional within the request (for example `run all` with the quality tier declined: discover, enrich, score can still run), the other stages run and one line names the skipped ones, for example `Skipping tailor, cover: quality model is not set up.` The same line is shown again in the final run summary.
- A stage whose own input needs are missing is never run partially. When a skipped stage is a prerequisite of a later stage, later stages that depend on it are named as skipped too. (What counts as required vs. optional: a requested stage is "required" when it is the only stage requested or every requested stage depends on the missing item; otherwise it is optional.)
- Exit code is 0 when the stages that ran succeeded, even if some were skipped by choice.

**No terminal, or `--no-prompt`.** Nothing is asked and nothing waits on input. The list is printed (same message, ending with `Run again after fixing these, or run in a terminal to be prompted.`), the exit code is 1, and no stage starts. `--no-prompt` is a new flag on both `run` and `apply`, in help as: `Never prompt; list missing settings and exit 1.` When nothing is missing, `--no-prompt` has no effect.

**When nothing is missing** the check prints nothing and the run proceeds exactly as before.

**Reachability.** For a configured tier the check may probe the endpoint (as `doctor` does), at most a few seconds per tier. An unreachable tier is shown as a warning line in the message, not as a missing item, and does not block the run (it is `WARN` in `doctor` today). No LLM completion is requested.

**Secrets.** API keys are never printed: not in prompts, not after saving, not in errors, not in the list. Answers are never guessed or defaulted other than the yes/no defaults above and the provider-specific defaults `init` already offers.

**Existing gates.** The existing `check_tier` gates and the existing apply checks (profile, tailored resumes, Chrome profile guard) remain as a backstop and keep their current messages; the new check runs before them so a user normally never sees them.

### Assets
None (no mock-ups). Reference behaviour: `src/hireember/wizard/init.py` (prompts), `hireember models set` in `src/hireember/cli.py`, `src/hireember/doctor.py` (checks and fix text), `src/hireember/location.py`.

## Acceptance criteria

- AC-1: `pytest` and `ruff check .` pass with the new and updated tests.
- AC-2: With the only target "Canada" (profile `country` = Canada, no other targets), "Calgary, AB", "Toronto, ON", "Vancouver, British Columbia" and "Montreal, QC, Canada" are not skipped. "Austin, TX" and "London, UK" are skipped, with status reason exactly `location: Austin, TX` and `location: London, UK`.
- AC-3: With the only target "Alberta" (no country), "Calgary, AB" is not skipped and "Toronto, ON" is skipped with reason `location: Toronto, ON`.
- AC-4: "Calgary" and "Greater Toronto Area" are not skipped. A bare `CA` is not skipped when the only target is "Canada" and not skipped when the only target is "California"; it is skipped when the only target is, for example, "Texas".
- AC-5: Remote, empty, placeholder and no-target cases return no skip, as in phase 0e. Phase 0e tests that expected a skip for text with no recognised region are changed to expect no skip; no other phase 0e test changes.
- AC-6: With the quality tier unconfigured, in a terminal, `hireember run tailor` prints the missing list naming the quality model, offers the model prompts (including `Use the same settings as the fast tier? [Y/n]` when the fast tier is configured), writes the answers to `models.toml` (same content `models set quality` would write; with "same as fast", the fast tier's values copied), and starts the tailor stage in the same process.
- AC-7: With the quality tier, the registered resume (or its text file) and the Playwright browser all missing, and a run that needs all three (for example `hireember run enrich tailor`), one message lists all three items with fixes, then the system prompts for them one at a time in listed order.
- AC-8: With stdin or stdout not a TTY, or with `--no-prompt`, nothing is prompted, the list is printed, the exit code is 1, and no stage starts (no database writes by stages, no network use). With nothing missing, behaviour is unchanged.
- AC-9: Declining the only required item exits 1 and prints the list of what is still missing. Declining an item needed only by an optional stage lets the other stages run and prints a line naming the skipped stages.
- AC-10: `hireember run discover` never asks or lists anything about model tiers. `hireember run score` asks about the fast tier only. `hireember run tailor cover` asks about the quality tier only. (`run enrich` asks only about the browser.)
- AC-11: `hireember apply` with Claude Code CLI or Chrome missing lists each one with its install pointer (the `doctor` text) and does not prompt for them, in a terminal or not; the exit code is 1 if they remain missing.
- AC-12: `run --dry-run`, `apply --dry-run`, `apply --mark-applied`, `apply --mark-failed` and `apply --reset-failed` perform no settings check, print no missing list and never prompt.
- AC-13: No API key value appears in any output of the check, its prompts, its confirmations or its errors (including when the key is entered or copied via "same as fast").
- AC-14: Stage behaviour, gating, the queue, wizard steps, `hireember doctor` output and `hireember models` output are unchanged; the check makes no LLM completion call (a reachability probe of at most a few seconds per tier is the only network use).
- AC-15 (implied by R5, R10): `--no-prompt` is accepted by both `run` and `apply` and listed in their `--help`.
- AC-16 (implied by R12): After a successful fix the run continues in the same process; the user is never asked to re-run the command, and an already-satisfied item is not asked about again.
- AC-17 (implied by R5, R7): A need is listed once even if several requested stages share it (for example a missing resume with `run score tailor` is one item naming both stages).

## Edge cases and errors

- Location: text such as "Washington, DC" or "Georgia" follows the existing table (DC and Georgia-the-state are US). "Remote, US" and "Hybrid - Toronto, ON" follow phase 0e remote/hybrid handling. Mixed-country text ("Toronto, ON / New York, NY") passes if either part fits (as today's per-part rule).
- Location: reject patterns and `location_reject_non_remote` still skip regardless of the new region-to-country rule.
- Check: user presses Ctrl-C or Ctrl-D (EOF) at a prompt: treated as declining everything remaining; the normal declining rules apply (exit 1 if a required item is missing). No traceback.
- Check: empty answer to provider/model/file path: asked again once, then treated as declined for that item. Nothing is guessed.
- Check: unreadable or unsupported resume path (not found, not .txt/.pdf, PDF with no extractable text): same error text as `init`; the offer repeats once, then declining applies.
- Check: `playwright install chromium` fails or `playwright` is not on PATH: show the failure and the manual command; item stays missing.
- Check: a registered resume exists but `resume.txt` is missing: counted as the missing-resume item and offered the resume prompt (re-register).
- Check: `models.toml` is malformed: listed as a missing/invalid tier with the parser's message and the `models set <tier>` fix; the fix overwrites only that tier.
- Check: tier configured but unreachable: warning only, run continues.
- Check: jobspy is needed only when a job board source is configured; a config with only career sites and Workday employers does not list jobspy.
- Check: `apply` with no tailored resumes ready lists `No tailored resumes ready. Run hireember run score tailor first.` and is not prompted; exit 1.
- Check: non-interactive and everything present: no output, run proceeds.
- Check slow: no step waits longer than the probe limit; nothing waits on input without a TTY.

## Out of scope
- Region data for countries other than Canada and the United States.
- New dependencies.
- Changing `doctor` or `models` output or behaviour (the check reuses `doctor` logic, it does not alter it).
- Installing Claude Code CLI, Chrome or jobspy for the user.
- Changing score/tailor/apply logic or the existing `check_tier` messages.

## Open questions
- A country-only text with a region target: with the target "Alberta", should "Calgary, Canada" or "Remote - Canada-wide" style text (country named, region not) be skipped or passed? Proposal: pass (the country matches the region's country, so it is not recognisably elsewhere); "Toronto, ON, Canada" still skipped because a different region is named. Needs confirmation.
- Declined-prerequisite behaviour in `run all`: confirm that when `tailor`/`cover` are skipped because the quality tier was declined, `pdf` is also skipped (it has nothing to render) rather than run on whatever exists.
- When "same as fast" is chosen and the fast tier's key is stored in an environment variable rather than `models.toml`, is copying the resolved key into `models.toml` acceptable? Answers say values are copied; this confirms it covers the env case.
