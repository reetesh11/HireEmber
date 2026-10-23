"""HireEmber CLI — the main entry point."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from hireember import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="hireember",
    help=("HireEmber — AI-powered end-to-end job application pipeline. "
          "Keep a company list, schedule daily runs, and export your results."),
    no_args_is_help=True,
)
console = Console()
log = logging.getLogger(__name__)

# Valid pipeline stages (in execution order)
VALID_STAGES = ("discover", "enrich", "score", "tailor", "cover", "pdf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    """Common setup: load env, create dirs, init DB."""
    from hireember.config import load_env, ensure_dirs
    from hireember.database import init_db

    load_env()
    ensure_dirs()
    init_db()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]hireember[/bold] {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """HireEmber — AI-powered end-to-end job application pipeline.

    Keep a company list, schedule daily runs, and export your results.
    """


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from hireember.wizard.init import run_wizard

    run_wizard()


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Defaults to 'all' if omitted."
        ),
    ),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    validation: str = typer.Option(
        "normal",
        "--validation",
        help=(
            "Validation strictness for tailor/cover stages. "
            "strict: banned words = errors, judge must pass. "
            "normal: banned words = warnings only (default, recommended for Gemini free tier). "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Never prompt; list missing settings and exit 1."),
) -> None:
    """Run pipeline stages: discover, enrich, score, tailor, cover, pdf.

    Exactly one of discover, score or tailor runs only that stage and prints its result.
    discover searches the company list (see `hireember company add`).
    """
    _bootstrap()

    from hireember.pipeline import run_pipeline

    stage_list = stages if stages else ["all"]

    # Validate stage names
    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            console.print(
                f"[red]Unknown stage:[/red] '{s}'. "
                f"Valid stages: {', '.join(VALID_STAGES)}, all"
            )
            raise typer.Exit(code=1)

    # Validate the --validation flag value
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    single_stage = (len(stage_list) == 1 and stage_list[0] in ("discover", "score", "tailor")
                    and not dry_run and not stream)
    if single_stage:
        from hireember import runs
        from hireember.database import get_connection

        if runs.is_running(get_connection()):
            console.print("A run is already in progress.", markup=False)
            raise typer.Exit(code=1)

    skipped_notes: list[str] = []
    if not dry_run:
        from hireember import preflight

        outcome = preflight.run_preflight("run", stage_list, no_prompt=no_prompt)
        if not outcome.proceed:
            raise typer.Exit(code=1)
        stage_list = outcome.stages
        skipped_notes = preflight.skip_notes(outcome.skipped)

    # Gate AI stages behind Tier 2
    llm_stages = {"score", "tailor", "cover"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        from hireember.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    if single_stage:
        try:
            outcome_msg = runs.run_stage(stage_list[0], min_score=min_score, validation_mode=validation)
        except runs.RunInProgressError as e:
            console.print(str(e), markup=False)
            raise typer.Exit(code=1)
        console.print(outcome_msg.message, markup=False, highlight=False)
        return

    kwargs = {"skipped_notes": skipped_notes} if skipped_notes else {}
    result = run_pipeline(
        stages=stage_list,
        min_score=min_score,
        dry_run=dry_run,
        stream=stream,
        workers=workers,
        validation_mode=validation,
        **kwargs,
    )

    if result.get("errors"):
        raise typer.Exit(code=1)


@app.command()
def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    model: str = typer.Option("haiku", "--model", "-m", help="Claude model name."),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers in headless mode."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
    review: bool = typer.Option(False, "--review", help="Stop before every submit so you can look at the form."),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Never prompt; list missing settings and exit 1."),
) -> None:
    """Launch auto-apply to submit job applications."""
    from hireember.config import is_linkedin_url

    if url and is_linkedin_url(url):
        console.print(f"[red]LinkedIn job URLs are not supported:[/red] {url}", soft_wrap=True)
        raise typer.Exit(code=1)

    _bootstrap()

    from hireember.config import check_tier, PROFILE_PATH as _profile_path
    from hireember.database import get_connection

    # --- Utility modes (no Chrome/Claude needed) ---

    if mark_applied:
        from hireember.apply.launcher import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return

    if mark_failed:
        from hireember.apply.launcher import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from hireember.apply.launcher import reset_failed as do_reset
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    # --- Full apply mode ---

    # Check 0: never touch the user's own Chrome profile
    from hireember.apply.chrome import DefaultProfileError, check_worker_profiles
    try:
        check_worker_profiles(workers)
    except DefaultProfileError as e:
        console.print(str(e), markup=False, soft_wrap=True)
        raise typer.Exit(code=1)

    if not dry_run:
        from hireember import preflight

        if not preflight.run_preflight("apply", [], no_prompt=no_prompt, gen_url=bool(gen and url)).proceed:
            raise typer.Exit(code=1)

    # Check 1: Tier 3 required (Claude Code CLI + Chrome)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not _profile_path.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]hireember init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]hireember run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from hireember.apply.launcher import gen_prompt
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print("\n[bold]Run manually:[/bold]")
        console.print(
            f"  claude --model {model} -p "
            f"--mcp-config {mcp_path} "
            f"--permission-mode bypassPermissions < {prompt_file}"
        )
        return

    from hireember.apply.launcher import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Model:    {model}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Dry run:  {dry_run}")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    from hireember import runs

    lock_conn = get_connection()
    try:
        token = runs.acquire_lock(lock_conn)
    except runs.RunInProgressError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(code=1)
    try:
        submitted = apply_main(
            limit=effective_limit,
            target_url=url,
            min_score=min_score,
            headless=headless,
            model=model,
            dry_run=dry_run,
            continuous=continuous,
            workers=workers,
            review=True if review else None,
        )
    finally:
        runs.release_lock(lock_conn, token)
    console.print(f"apply: {submitted or 0} submitted.", markup=False)


@app.command()
def status() -> None:
    """Show pipeline statistics from the database."""
    _bootstrap()

    from hireember.database import get_stats

    stats = get_stats()

    console.print("\n[bold]HireEmber Pipeline Status[/bold]\n")

    # Summary table
    summary = Table(title="Pipeline Overview", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Count", justify="right")

    summary.add_row("Total jobs discovered", str(stats["total"]))
    summary.add_row("With full description", str(stats["with_description"]))
    summary.add_row("Pending enrichment", str(stats["pending_detail"]))
    summary.add_row("Enrichment errors", str(stats["detail_errors"]))
    summary.add_row("Scored by LLM", str(stats["scored"]))
    summary.add_row("Pending scoring", str(stats["unscored"]))
    summary.add_row("Skipped by location", str(stats["location_skipped"]))
    summary.add_row("Tailored resumes", str(stats["tailored"]))
    summary.add_row("Pending tailoring (7+)", str(stats["untailored_eligible"]))
    summary.add_row("Cover letters", str(stats["with_cover_letter"]))
    summary.add_row("Ready to apply", str(stats["ready_to_apply"]))
    summary.add_row("Applied", str(stats["applied"]))
    summary.add_row("Apply errors", str(stats["apply_errors"]))

    console.print(summary)

    # Score distribution
    if stats["score_distribution"]:
        dist_table = Table(title="\nScore Distribution", show_header=True, header_style="bold yellow")
        dist_table.add_column("Score", justify="center")
        dist_table.add_column("Count", justify="right")
        dist_table.add_column("Bar")

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 30)
            if score >= 7:
                color = "green"
            elif score >= 5:
                color = "yellow"
            else:
                color = "red"
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            dist_table.add_row(str(score), str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        site_table = Table(title="\nJobs by Source", show_header=True, header_style="bold magenta")
        site_table.add_column("Site")
        site_table.add_column("Count", justify="right")

        for site, count in stats["by_site"]:
            site_table.add_row(site or "Unknown", str(count))

        console.print(site_table)

    # Tickets that need a human
    from hireember.database import get_connection

    blocked = get_connection().execute(
        "SELECT t.id, j.title, t.status, t.status_reason, t.not_before FROM tickets t "
        "LEFT JOIN jobs j ON j.url = t.job_url WHERE t.status = 'blocked for human' "
        "OR (t.status = 'pending' AND t.status_reason LIKE 'limit:%') ORDER BY t.id"
    ).fetchall()
    if blocked:
        attention = Table(title="\nTickets needing attention", show_header=True, header_style="bold red")
        attention.add_column("Ticket")
        attention.add_column("Job", overflow="fold")
        attention.add_column("Status")
        attention.add_column("Reason", overflow="fold")
        for ticket_id, title, status_name, reason, not_before in blocked:
            reason = reason or ""
            if not_before and "until" not in reason:
                reason += f" (until {not_before[:16].replace('T', ' ')})"
            attention.add_row(str(ticket_id), title or "", status_name, reason)
        console.print(attention)

    console.print()


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Address to bind (only 127.0.0.1 is allowed)."),
    port: int = typer.Option(8765, "--port", help="Port to listen on."),
    open: bool = typer.Option(False, "--open", help="Open the dashboard in your browser."),
) -> None:
    """Open the local web dashboard."""
    _bootstrap()

    import errno

    from hireember.web.server import HostRefusedError, serve

    try:
        serve(host, port, open)
    except HostRefusedError as exc:
        console.print(str(exc), markup=False)
        raise typer.Exit(code=2)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        console.print(f"Port {port} is already in use. Choose another with --port.", markup=False)
        raise typer.Exit(code=1)


@app.command()
def doctor() -> None:
    """Check your setup and diagnose missing requirements."""
    from rich.markup import escape

    from hireember.config import load_env
    from hireember.doctor import run_checks

    load_env()

    styles = {"OK": "green", "MISSING": "red", "WARN": "yellow", "optional": "dim"}
    results = run_checks()

    # --- Render results ---
    console.print()
    console.print("[bold]HireEmber Doctor[/bold]\n")

    col_w = max(len(r.name) for r in results) + 2
    for r in results:
        pad = " " * (col_w - len(r.name))
        style = styles.get(r.status, "white")
        console.print(
            f"  {escape(r.name)}{pad}[{style}]{r.status}[/{style}]  [dim]{escape(r.note)}[/dim]",
            soft_wrap=True,
        )

    console.print()

    # Tier summary
    from hireember.config import get_tier, TIER_LABELS
    tier = get_tier()
    console.print(f"[bold]Current tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]")

    if tier == 1:
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs a configured model, see hireember models show)[/dim]")
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Claude Code CLI + Chrome + Node.js 18+)[/dim]")
    elif tier == 2:
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Claude Code CLI + Chrome + Node.js 18+)[/dim]")

    console.print()


# ---------------------------------------------------------------------------
# Answer bank and question queue
# ---------------------------------------------------------------------------

answers_app = typer.Typer(help="Stored answers to application questions.", no_args_is_help=True)
queue_app = typer.Typer(help="Questions waiting for your answer.", no_args_is_help=True)
app.add_typer(answers_app, name="answers")
app.add_typer(queue_app, name="queue")


@answers_app.command("list")
def answers_list() -> None:
    """Show every stored answer."""
    _bootstrap()

    from hireember.answers import list_answers
    from hireember.database import get_connection

    rows = list_answers(get_connection())
    if not rows:
        console.print('No answers stored yet. Run "hireember init" or answer queued questions.')
        return
    table = Table(title="Answers", show_header=True, header_style="bold cyan")
    for column in ("Question", "Key", "Answer", "Source", "Last used", "Used"):
        table.add_column(column)
    for r in rows:
        table.add_row(r["question_text"], r["normalized_key"], r["answer"], r["source"],
                      r["last_used_at"] or "never", str(r["times_used"] or 0))
    console.print(table)


@queue_app.command("list")
def queue_list() -> None:
    """Show open queue items."""
    _bootstrap()

    from hireember.answers import list_queue
    from hireember.database import get_connection

    items = list_queue(get_connection())
    if not items:
        console.print("No open queue items.")
        return
    table = Table(title="Queue", show_header=True, header_style="bold cyan")
    for column in ("Id", "Ticket", "Kind", "Company", "Page", "Question"):
        table.add_column(column, overflow="fold")
    for i in items:
        table.add_row(str(i["id"]), str(i["ticket_id"] or ""), i["kind"] or "", i["company"] or "",
                      i["page_link"] or "", i["question_text"] or "")
    console.print(table)


@queue_app.command("answer")
def queue_answer(
    item_id: int = typer.Argument(..., help="Queue item id."),
    answer: str = typer.Argument(..., help="Your answer."),
) -> None:
    """Answer a queued question and return its ticket to pending."""
    _bootstrap()

    from hireember.answers import QueueError, answer_queue_item
    from hireember.database import get_connection

    try:
        result = answer_queue_item(get_connection(), item_id, answer)
    except QueueError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(result.message, markup=False)


@queue_app.command("ready")
def queue_ready(item_id: int = typer.Argument(..., help="Queue item id.")) -> None:
    """Mark a handled item (sign-in, CAPTCHA, review...) ready and return its ticket to pending."""
    _bootstrap()

    from hireember.answers import QueueError, ready_queue_item
    from hireember.database import get_connection

    try:
        result = ready_queue_item(get_connection(), item_id)
    except QueueError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(result.message, markup=False)


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

company_app = typer.Typer(
    help="The companies HireEmber searches, and the manual-only flag.", no_args_is_help=True)
app.add_typer(company_app, name="company")


@company_app.command("manual")
def company_manual(
    name: str = typer.Argument(..., help="Company name."),
    off: bool = typer.Option(False, "--off", help="Remove the manual-only flag."),
) -> None:
    """Mark a company as manual-only: its tickets wait for you instead of the agent."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.tickets import CompanyNotFoundError, set_company_manual

    try:
        set_company_manual(get_connection(), name, not off)
    except CompanyNotFoundError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    state = "no longer manual-only" if off else "now manual-only"
    console.print(f'Company "{name}" is {state}.', markup=False)


@company_app.command("add", help="Add a company to the list discovery searches.")
def company_add(
    name: str = typer.Argument(..., help="Company name."),
    url: str = typer.Option(..., "--url", help="Careers page URL."),
    ats: str = typer.Option(..., "--ats", help="ATS type: workday or careers-page."),
) -> None:
    """Add a company to the list discovery searches."""
    _bootstrap()

    from hireember.companies import add_company
    from hireember.database import get_connection
    from hireember.tickets import TicketError

    try:
        add_company(get_connection(), name, url, ats)
    except TicketError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(f'Added company "{name}".', markup=False)


@company_app.command("remove", help="Take a company off the list discovery searches.")
def company_remove(name: str = typer.Argument(..., help="Company name.")) -> None:
    """Take a company off the list discovery searches. Its past jobs and tickets stay."""
    _bootstrap()

    from hireember.companies import remove_company
    from hireember.database import get_connection
    from hireember.tickets import TicketError

    try:
        remove_company(get_connection(), name)
    except TicketError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(f'Removed company "{name}".', markup=False)


@company_app.command("list")
def company_list() -> None:
    """Show every company on the list, its careers page, ATS and manual-only flag."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.tickets import list_companies

    rows = list_companies(get_connection())
    if not rows:
        console.print("No companies yet.")
        return
    table = Table(title="Companies", show_header=True, header_style="bold cyan")
    for column in ("Id", "Name", "Careers URL", "ATS", "Manual-only"):
        table.add_column(column, overflow="fold")
    for r in rows:
        table.add_row(str(r["id"]), r["name"], r["careers_url"], r["ats_type"],
                      "yes" if r["manual_only"] else "no")
    console.print(table)


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def _applying_line(schedule) -> str:
    if schedule.apply:
        return f"Scheduled applying: on (up to {schedule.apply_limit} per day)."
    return "Scheduled applying: off."


@app.command(help="Show or set the daily times for scheduled runs, and whether they may apply.")
def schedule(
    at: Optional[list[str]] = typer.Option(
        None, "--at", help="Daily run time, 24-hour HH:MM (repeat for several), e.g. --at 08:00."),
    off: bool = typer.Option(False, "--off", help="Clear the schedule."),
    apply: Optional[str] = typer.Option(
        None, "--apply", help="Let scheduled runs apply to jobs: on or off (default off)."),
    apply_limit: Optional[int] = typer.Option(
        None, "--apply-limit", help="Most applications scheduled runs make per day (default 25)."),
) -> None:
    """Show or set the daily times for scheduled runs. Runs fire only while `hireember scheduler` runs."""
    _bootstrap()

    from hireember import scheduler
    from hireember.database import get_connection

    conn = get_connection()
    if apply is not None and apply not in ("on", "off"):
        console.print('Invalid --apply value "%s". Use on or off.' % apply, markup=False)
        raise typer.Exit(code=1)
    if apply_limit is not None and apply_limit < 1:
        console.print("The apply limit must be at least 1.", markup=False)
        raise typer.Exit(code=1)
    try:
        times = sorted({scheduler.parse_time(t) for t in at or []})
    except scheduler.ScheduleError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(code=1)

    changed = False
    if apply is not None or apply_limit is not None:
        scheduler.set_apply(conn, on=None if apply is None else apply == "on", limit=apply_limit)
        changed = True
    if off:
        scheduler.clear_schedule(conn)
        console.print("Schedule cleared.", markup=False)
        changed = True
    elif times:
        scheduler.set_schedule(conn, times)
        console.print(f"Schedule set: daily at {', '.join(times)}.", markup=False)
        console.print(
            "Runs fire only while `hireember scheduler` is running. A run missed while it was "
            "not running starts once at the next start.", markup=False)
        changed = True

    current = scheduler.get_schedule(conn)
    if at or off:
        return
    if not changed:
        line = f"Scheduled daily at {', '.join(current.times)}." if current.times else "No schedule set."
        console.print(line, markup=False)
    console.print(_applying_line(current), markup=False)


@app.command(help="Run in the foreground and start scheduled runs when their time comes.")
def scheduler(
    once: bool = typer.Option(False, "--once", help="Check for a due run once and exit."),
    poll_seconds: float = typer.Option(30, "--poll-seconds", help="Seconds between checks."),
) -> None:
    """Run in the foreground and start scheduled runs when their time comes."""
    _bootstrap()

    from hireember import scheduler as scheduler_mod

    if not once:
        console.print("Scheduler running. Press Ctrl+C to stop.", markup=False)
    try:
        scheduler_mod.serve(poll_seconds=poll_seconds, once=once)
    except KeyboardInterrupt:
        console.print("Scheduler stopped.", markup=False)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

@app.command("export", help="Write your tickets and runs to tickets.csv and runs.csv.")
def export_command(
    out: str = typer.Option(".", "--out", help="Folder to write tickets.csv and runs.csv into."),
) -> None:
    """Write your tickets and your runs to two CSV files (tickets.csv and runs.csv)."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.export import ExportError, export_csv

    try:
        results = export_csv(get_connection(), out)
    except ExportError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(code=1)
    for path, count in results:
        console.print(f"Wrote {path} ({count} rows).", markup=False, soft_wrap=True)


# ---------------------------------------------------------------------------
# Model tiers
# ---------------------------------------------------------------------------

models_app = typer.Typer(help="Model tiers: fast and quality.", no_args_is_help=True)
app.add_typer(models_app, name="models")


def _say(text: str) -> None:
    console.print(text, markup=False, highlight=False)


@models_app.command("show")
def models_show() -> None:
    """Show the settings of both tiers. API keys are never printed."""
    from hireember import models

    try:
        models.load_models_file()
    except models.ModelsError as e:
        _say(str(e))
        raise typer.Exit(1)
    _say("Model tiers")
    for tier in models.TIERS:
        _say("")
        _say(tier)
        try:
            s = models.resolve_tier(tier)
        except models.ModelsError as e:
            _say(f"  {e}" if "not configured" not in str(e) else "  not configured")
            if "not configured" in str(e):
                _say(f"  Run 'hireember models set {tier}' or 'hireember init'.")
            continue
        _say(f"  provider: {s.provider}")
        _say(f"  model:    {s.model}")
        _say(f"  base url: {s.base_url}" + (" (preset)" if s.provider != "custom" else ""))
        _say(f"  key:      {models.key_origin(s)}")
        _say(f"  source:   {s.source}")


@models_app.command("set")
def models_set(
    tier: str = typer.Argument(..., help="fast or quality."),
    provider: Optional[str] = typer.Option(None, "--provider", help="gemini, openai or custom."),
    model: Optional[str] = typer.Option(None, "--model", help="Model name."),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Endpoint URL (custom provider)."),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key, stored in models.toml."),
) -> None:
    """Change one tier's settings; fields you leave out are kept."""
    from hireember import models

    if tier not in models.TIERS:
        _say("Tier must be 'fast' or 'quality'.")
        raise typer.Exit(1)
    if provider is None and model is None and base_url is None and api_key is None:
        _say("Nothing to change. Pass --provider, --model, --base-url or --api-key.")
        raise typer.Exit(1)
    try:
        path = models.save_tier(tier, provider=provider, model=model, base_url=base_url, api_key=api_key)
    except (models.ModelsError, ValueError) as e:
        _say(str(e))
        raise typer.Exit(1)
    _say(f"Saved {tier} tier to {path}.")


@models_app.command("test")
def models_test() -> None:
    """Make one tiny request per tier and report whether it worked."""
    from hireember import models

    failed = False
    for tier in models.TIERS:
        r = models.test_tier(tier)
        if r.ok:
            _say(f"{tier:<9}{'ok':<9}{r.model} ({r.seconds:.1f}s)")
        else:
            failed = True
            _say(f"{tier:<9}{'FAILED':<9}{r.message}")
    if failed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Ticket details
# ---------------------------------------------------------------------------

ticket_app = typer.Typer(help="Ticket details.", no_args_is_help=True)
app.add_typer(ticket_app, name="ticket")


@ticket_app.command("log")
def ticket_log(ticket_id: int = typer.Argument(..., help="Ticket id.")) -> None:
    """Show what each apply attempt did on a ticket."""
    _bootstrap()

    from hireember.apply.attempts import get_log
    from hireember.database import get_connection
    from hireember.tickets import TicketNotFoundError, get_ticket

    conn = get_connection()
    try:
        ticket = get_ticket(conn, ticket_id)
    except TicketNotFoundError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    reason = f" ({ticket['status_reason']})" if ticket["status_reason"] else ""
    console.print(f"Status: {ticket['status']}{reason}", markup=False, highlight=False)
    rows = get_log(conn, ticket_id)
    if not rows:
        console.print(f"No attempts logged for ticket {ticket_id}.")
        return
    table = Table(title=f"Ticket {ticket_id} log", show_header=True, header_style="bold cyan")
    for column in ("Attempt", "Time", "Step", "Field", "Source", "Detail"):
        table.add_column(column, overflow="fold")
    for r in rows:
        table.add_row(str(r["attempt"]), r["time"], r["kind"], r["field"] or "",
                      r["source"] or "", r["detail"] or "")
    console.print(table)


# ---------------------------------------------------------------------------
# Base resumes
# ---------------------------------------------------------------------------

resume_app = typer.Typer(help="Base resumes used for scoring and tailoring.", no_args_is_help=True)
app.add_typer(resume_app, name="resume")


@resume_app.command("add")
def resume_add(
    file: str = typer.Argument(..., help="Resume file (.txt or .pdf)."),
    name: str = typer.Option(..., "--name", help="Name for this resume."),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags, matched against job titles."),
    text: Optional[str] = typer.Option(None, "--text", help="Plain-text copy of a PDF resume."),
) -> None:
    """Add a base resume."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.resumes import ResumeError, add_resume

    try:
        resume_id = add_resume(get_connection(), file, name, tags, text_file=text)
    except ResumeError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(f"Added resume {resume_id}: {name}.", markup=False)


@resume_app.command("list")
def resume_list() -> None:
    """Show base resumes."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.resumes import list_resumes

    rows = list_resumes(get_connection())
    if not rows:
        console.print('No base resumes. Add one with "hireember resume add".')
        return
    table = Table(title="Base resumes", show_header=True, header_style="bold cyan")
    for column in ("Id", "Name", "Tags", "Pinned", "File", "Added"):
        table.add_column(column)
    for r in rows:
        table.add_row(str(r["id"]), r["name"], ", ".join(r["tags"]), "yes" if r["pinned"] else "",
                      r["file_path"], r["added_at"] or "")
    console.print(table)


@resume_app.command("pin")
def resume_pin(resume_id: int = typer.Argument(..., help="Resume id.")) -> None:
    """Always use this resume."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.resumes import ResumeError, pin_resume

    try:
        pin_resume(get_connection(), resume_id)
    except ResumeError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
    console.print(f"Pinned resume {resume_id}.", markup=False)


@resume_app.command("unpin")
def resume_unpin() -> None:
    """Go back to choosing the best fit per job."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.resumes import unpin_resume

    unpin_resume(get_connection())
    console.print("Unpinned.")


if __name__ == "__main__":
    app()
