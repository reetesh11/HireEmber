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
    help="HireEmber — AI-powered end-to-end job application pipeline.",
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
    """HireEmber — AI-powered end-to-end job application pipeline."""


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
) -> None:
    """Run pipeline stages: discover, enrich, score, tailor, cover, pdf."""
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

    # Gate AI stages behind Tier 2
    llm_stages = {"score", "tailor", "cover"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        from hireember.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    # Validate the --validation flag value
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    result = run_pipeline(
        stages=stage_list,
        min_score=min_score,
        dry_run=dry_run,
        stream=stream,
        workers=workers,
        validation_mode=validation,
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

    apply_main(
        limit=effective_limit,
        target_url=url,
        min_score=min_score,
        headless=headless,
        model=model,
        dry_run=dry_run,
        continuous=continuous,
        workers=workers,
    )


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
        "SELECT t.id, j.title, t.status, t.status_reason FROM tickets t "
        "LEFT JOIN jobs j ON j.url = t.job_url WHERE t.status = 'blocked for human' ORDER BY t.id"
    ).fetchall()
    if blocked:
        attention = Table(title="\nTickets needing attention", show_header=True, header_style="bold red")
        attention.add_column("Ticket")
        attention.add_column("Job", overflow="fold")
        attention.add_column("Status")
        attention.add_column("Reason", overflow="fold")
        for ticket_id, title, status_name, reason in blocked:
            attention.add_row(str(ticket_id), title or "", status_name, reason or "")
        console.print(attention)

    console.print()


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from hireember.view import open_dashboard

    open_dashboard()


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
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs LLM API key)[/dim]")
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
    for column in ("Id", "Ticket", "Kind", "Question"):
        table.add_column(column)
    for i in items:
        table.add_row(str(i["id"]), str(i["ticket_id"] or ""), i["kind"] or "", i["question_text"] or "")
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


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------

company_app = typer.Typer(help="Companies and the manual-only flag.", no_args_is_help=True)
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


@company_app.command("list")
def company_list() -> None:
    """Show every company and whether it is manual-only."""
    _bootstrap()

    from hireember.database import get_connection
    from hireember.tickets import list_companies

    rows = list_companies(get_connection())
    if not rows:
        console.print("No companies yet.")
        return
    table = Table(title="Companies", show_header=True, header_style="bold cyan")
    for column in ("Id", "Name", "Manual-only"):
        table.add_column(column)
    for r in rows:
        table.add_row(str(r["id"]), r["name"], "yes" if r["manual_only"] else "no")
    console.print(table)


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
        get_ticket(conn, ticket_id)
    except TicketNotFoundError as e:
        console.print(str(e), markup=False)
        raise typer.Exit(1)
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
