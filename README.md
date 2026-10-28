<!-- logo here -->

> **⚠️ ApplyPilot** is the original open-source project, created by [Pickle-Pixel](https://github.com/Pickle-Pixel) and first published on GitHub on **February 17, 2026**. We are **not affiliated** with applypilot.app, useapplypilot.com, or any other product using the "ApplyPilot" name. These sites are **not associated with this project** and may misrepresent what they offer. If you're looking for the autonomous, open-source job application agent — you're in the right place.

## Fork notice

HireEmber/OpenApply is a fork of [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) by [Pickle-Pixel](https://github.com/Pickle-Pixel). It is distributed under the same license, AGPL-3.0 (GNU Affero General Public License v3.0), and the original copyright notices and attribution are kept intact. The rest of this README is the upstream ApplyPilot documentation, adapted where the fork differs.

# HireEmber

**Applied to 1,000 jobs in 2 days. Fully autonomous. Open source.**

[![PyPI version](https://img.shields.io/pypi/v/hireember?color=blue)](https://pypi.org/project/hireember/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Pickle-Pixel/ApplyPilot?style=social)](https://github.com/Pickle-Pixel/ApplyPilot)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/S6S01UL5IO)




https://github.com/user-attachments/assets/7ee3417f-43d4-4245-9952-35df1e77f2df


---

## What It Does

ApplyPilot is a 6-stage autonomous job application pipeline. It discovers jobs across 5+ boards, scores them against your resume with AI, tailors your resume per job, writes cover letters, and **submits applications for you**. It navigates forms, uploads documents, answers screening questions, all hands-free.

Three commands. That's it.

```bash
pip install hireember
hireember init           # one-time setup: resume, profile, preferences, API keys
hireember doctor         # verify your setup — shows what's installed and what's missing
hireember run            # discover > enrich > score > tailor > cover letters
hireember run -w 4       # same but parallel (4 threads for discovery/enrichment)
hireember apply          # autonomous browser-driven submission
hireember apply -w 3     # parallel apply (3 Chrome instances)
hireember apply --dry-run   # fill forms without submitting
```

`hireember init` asks for one resume file (.pdf, .txt or .docx). A PDF is read locally into an editable `resume.txt` in the data folder, and the name, contact and location found in it are offered as defaults in the profile step.

> `pip install hireember` is enough: job board scraping (`python-jobspy`) installs with it. Run `hireember doctor` afterwards to check the rest.

---

## Setup to your first scored role

You do not edit any code. You need Python 3.11 or later and a model API key (Gemini has a free tier).

1. Install: `pip install hireember`.
2. Run `hireember init`. It asks for your resume (.pdf, .txt or .docx), your profile, your job search and your API key.
3. Run `hireember doctor` and fix anything it reports as missing.
4. Run the discovery stage: `hireember run discover`. It searches the companies and job boards you set up.
5. Run the scoring stage: `hireember run score`. Each job gets a score from 1 to 10 and a short reason, and a ticket.
6. Open the dashboard with `hireember dashboard`, then open `http://127.0.0.1:8765`. Your first scored role is on the board, with its score and reason.

Notes: the safety rules are in [docs/safety.md](docs/safety.md). Each run and each apply attempt writes a log
file that the dashboard links to.

---

## Two Paths

### Full Pipeline (recommended)
**Requires:** Python 3.11+, Node.js (for npx), Gemini API key (free), Claude Code CLI, Chrome

Runs all 6 stages, from job discovery to autonomous application submission. This is the full power of ApplyPilot.

### Discovery + Tailoring Only
**Requires:** Python 3.11+, Gemini API key (free)

Runs stages 1-5: discovers jobs, scores them, tailors your resume, generates cover letters. You submit applications manually with the AI-prepared materials.

---

## The Pipeline

| Stage | What Happens |
|-------|-------------|
| **1. Discover** | Scrapes 5 job boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs) + the companies on your company list (`hireember company add`) + 30 direct career sites |
| **2. Enrich** | Fetches full job descriptions via JSON-LD, CSS selectors, or AI-powered extraction |
| **3. Score** | AI rates every job 1-10 based on your resume and preferences. Only high-fit jobs proceed |
| **4. Tailor** | AI rewrites your resume per job: reorganizes, emphasizes relevant experience, adds keywords. Never fabricates |
| **5. Cover Letter** | AI generates a targeted cover letter per job |
| **6. Auto-Apply** | Claude Code navigates application forms, fills fields, uploads documents, answers questions, and submits |

Each stage is independent. Run them all or pick what you need.

---

## ApplyPilot vs The Alternatives

| Feature | ApplyPilot | AIHawk | Manual |
|---------|-----------|--------|--------|
| Job discovery | 5 boards + Workday + direct sites | LinkedIn only | One board at a time |
| AI scoring | 1-10 fit score per job | Basic filtering | Your gut feeling |
| Resume tailoring | Per-job AI rewrite | Template-based | Hours per application |
| Auto-apply | Full form navigation + submission | LinkedIn Easy Apply only | Click, type, repeat |
| Supported sites | Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, 46 Workday portals, 28 direct sites | LinkedIn | Whatever you open |
| License | AGPL-3.0 | MIT | N/A |

---

## Requirements

| Component | Required For | Details |
|-----------|-------------|---------|
| Python 3.11+ | Everything | Core runtime |
| Node.js 18+ | Auto-apply | Needed for `npx` to run Playwright MCP server |
| Gemini API key | Scoring, tailoring, cover letters | Free tier (15 RPM / 1M tokens/day) is enough |
| Chrome/Chromium | Auto-apply | Auto-detected on most systems |
| Claude Code CLI | Auto-apply | Install from [claude.ai/code](https://claude.ai/code) |

**Gemini API key is free.** Get one at [aistudio.google.com](https://aistudio.google.com). OpenAI and local models (Ollama/llama.cpp) are also supported.

---

## Configuration

All generated by `hireember init`:

### `profile.json`
Your personal data in one structured file: contact info, work authorization, compensation, experience, skills, resume facts (preserved during tailoring), and EEO defaults. Powers scoring, tailoring, and form auto-fill.

### `searches.yaml`
Job search queries, target titles, locations, boards. Run multiple searches with different parameters.

### `.env`
API keys and runtime config: `GEMINI_API_KEY`, `LLM_MODEL`.

### Package configs (shipped with HireEmber)
- `config/employers.yaml` - A few Workday employer examples (your own list lives in the database: `hireember company add`)
- `config/sites.yaml` - Direct career sites (30+), blocked sites, base URLs, manual ATS domains
- `config/searches.example.yaml` - Example search configuration

---

## How Stages Work

### Discover
Queries Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs via JobSpy. Searches the companies on your company list (add with `hireember company add`). Hits 30 direct career sites with custom extractors. Deduplicates by URL.

### Enrich
Visits each job URL and extracts the full description. 3-tier cascade: JSON-LD structured data, then CSS selector patterns, then AI-powered extraction for unknown layouts.

### Score
AI scores every job 1-10 against your profile. 9-10 = strong match, 7-8 = good, 5-6 = moderate, 1-4 = skip. Only jobs above your threshold proceed to tailoring.

### Tailor
Generates a custom resume per job: reorders experience, emphasizes relevant skills, incorporates keywords from the job description. Your `resume_facts` (companies, projects, metrics) are preserved exactly. The AI reorganizes but never fabricates.

### Cover Letter
Writes a targeted cover letter per job referencing the specific company, role, and how your experience maps to their requirements.

### Auto-Apply
Claude Code launches a Chrome instance, navigates to each application page, detects the form type, fills personal information and work history, uploads the tailored resume and cover letter, answers screening questions with AI, and submits. A live dashboard shows progress in real-time.

The Playwright MCP server is configured automatically at runtime per worker. No manual MCP setup needed.

```bash
# Utility modes (no Chrome/Claude needed)
hireember apply --mark-applied URL     # manually mark a job as applied
hireember apply --mark-failed URL      # manually mark a job as failed
hireember apply --reset-failed         # reset all failed jobs for retry
hireember apply --gen --url URL        # generate prompt file for manual debugging
```

---

## CLI Reference

```
hireember init                          # First-time setup wizard
hireember doctor                        # Verify setup, diagnose missing requirements
hireember run [stages...]               # Run pipeline stages (or 'all')
hireember run --workers 4               # Parallel discovery/enrichment
hireember run --stream                  # Concurrent stages (streaming mode)
hireember run --min-score 8             # Override score threshold
hireember run --dry-run                 # Preview without executing
hireember run --validation lenient      # Relax validation (recommended for Gemini free tier)
hireember run --validation strict       # Strictest validation (retries on any banned word)
hireember apply                         # Launch auto-apply
hireember apply --workers 3             # Parallel browser workers
hireember apply --dry-run               # Fill forms without submitting
hireember apply --continuous            # Run forever, polling for new jobs
hireember apply --headless              # Headless browser mode
hireember apply --url URL               # Apply to a specific job
hireember status                        # Pipeline statistics
hireember dashboard                     # Open the local web dashboard
hireember company add "Acme" --url https://acme.wd3.myworkdayjobs.com/Careers --ats workday
hireember company list                  # Companies discovery searches
hireember company remove "Acme"
hireember schedule --at 08:00           # Run every day at 08:00 (repeat --at for more times)
hireember scheduler                     # Keep running so scheduled runs fire
hireember run discover                  # Run one stage (also score, tailor) and print its result
hireember export --out ./exports        # Write tickets.csv and runs.csv
```

### Company list

Discovery searches exactly the companies on your list. Add one with its careers page and ATS type:
`workday` (a `https://<tenant>.wd<N>.myworkdayjobs.com/<site>` address) or `careers-page` (any
other careers page, read with the AI extractor). `hireember company remove` takes a company off the
list; its past jobs and tickets stay. `hireember run discover` searches only this list.

### Scheduled runs

`hireember schedule --at 08:00 --at 18:30` sets the daily times; `hireember schedule` shows them and
`hireember schedule --off` clears them. Each scheduled run discovers, enriches, scores and tailors,
then writes one summary row you can see on the dashboard's Runs tab and in `hireember export`.
Only one run happens at a time: a second trigger (scheduler, command line or dashboard) is refused
with "A run is already in progress."

Runs fire only while `hireember scheduler` is running. It is a foreground process that checks every
30 seconds; start it at login, for example:

```
# cron (crontab -e)
@reboot hireember scheduler >> ~/.hireember/scheduler.log 2>&1
# systemd user unit: ExecStart=hireember scheduler   (systemctl --user enable --now hireember-scheduler)
# macOS launchd: a LaunchAgent with ProgramArguments ["hireember", "scheduler"] and RunAtLoad true
```

Schedules do not fire while the machine is asleep or off. A run missed that way is not lost: when
the scheduler is next started it launches one run (never one per missed time), so a missed run
starts at the next start after the machine wakes.
`hireember scheduler --once` checks once and exits, for use from cron or launchd directly.

Scheduled applying is off by default. `hireember schedule --apply on` lets scheduled runs apply to
jobs, up to `--apply-limit N` per day (default 25) minus what was already submitted today.

### Web dashboard

`hireember dashboard` starts a local web dashboard at `http://127.0.0.1:8765` (use `--port` to
change the port and `--open` to open your browser). It has a ticket board and list with filters,
a blocked queue where you can answer questions, answer and resume editing, notes, and CSV export.
It only binds to `127.0.0.1`; any other `--host` is refused. Press Ctrl+C to stop it.

### Answers, queue and base resumes

```
hireember answers list                  # Stored answers to application questions
hireember queue list                    # Questions waiting for your answer
hireember queue answer 3 "Blue"         # Answer queued item 3 and resume its ticket
hireember resume add cv.txt --name "Backend" --tags "backend,python"
hireember resume list                   # Base resumes
hireember resume pin 1                  # Always use resume 1 (hireember resume unpin to clear)
hireember resume delete 2               # Remove resume 2 (refused while a ticket uses it)
```

Scoring now needs at least one base resume: run `hireember resume add` first, or tickets are
blocked with `no base resume`. For a PDF, add a plain-text copy with `--text cv.txt` so it can be scored.
Passwords, tokens, payment details and government IDs are never stored; questions that ask for them
are queued and the ticket stays blocked for you.

### Resume library

Add base resumes as `.pdf`, `.txt` or `.docx` files (up to 10 MB), from the dashboard Resumes tab or with
`hireember resume add`. Each resume is read into text, split into sections (summary, experience, education,
skills) and short chunks, and stored in the local database with a keyword search index. Scoring, tailoring
and form-filling add the chunks that best match the job to their prompts (5 by default; set the
`resume_context_chunks` setting to change it). The Resumes tab shows each resume's extraction status and chunk
count, and lets you re-extract, replace the file or delete it. A scanned PDF has no text layer: there is no OCR,
so add a text copy (`--text`) or a text-based PDF. `.docx` reading uses the `python-docx` package, installed
with HireEmber.

Resume text extraction and search run entirely on your machine. Resume text leaves it only inside the prompts the pipeline already sends to your configured model.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

---

## License

HireEmber, like upstream ApplyPilot, is licensed under the [GNU Affero General Public License v3.0](LICENSE).

You are free to use, modify, and distribute this software. If you deploy a modified version as a service, you must release your source code under the same license.

## Start-of-run settings check

`hireember run` and `hireember apply` first check that the settings the requested stages need are in place (model tiers, resume, profile, search config, Playwright browser, Claude Code and Chrome for apply). In a terminal, missing items are listed once and you are offered to set them up on the spot. Declining an item skips the stages that need it. Without a terminal, or with `--no-prompt`, the list is printed and the command exits 1. `--dry-run` and the `apply` utility modes skip the check.
