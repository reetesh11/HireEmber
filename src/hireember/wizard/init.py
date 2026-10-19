"""HireEmber first-time setup wizard.

Interactive flow that creates ~/.hireember/ with:
  - resume.txt (and optionally resume.pdf)
  - profile.json
  - searches.yaml
  - .env (LLM API key)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from rich.prompt import Confirm, Prompt

from hireember.config import (
    APP_DIR,
    ENV_PATH,
    PROFILE_PATH,
    SEARCH_CONFIG_PATH,
    ensure_dirs,
)
from hireember import answers, config, resumes
from hireember.resume_extract import MIN_TEXT_CHARS, extract_pdf_text, propose_profile
from hireember.database import init_db
from hireember.profile import PROFILE_GROUPS, build_profile, group_complete, stored_answer

console = Console()


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

MASTER_RESUME_NAME = "Master resume"
_MARKER_NAME = ".resume_txt_sha256"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _marker() -> Path:
    return config.APP_DIR / _MARKER_NAME


def _is_user_supplied_txt() -> bool:
    """resume.txt counts as extracted only when the marker matches its current hash."""
    try:
        return _marker().read_text(encoding="utf-8").strip() != _sha256(config.RESUME_PATH)
    except OSError:
        return True


def _clean_path(raw: str) -> Path:
    return Path(str(raw).strip().strip('"').strip("'")).expanduser().resolve()


def _ask_file(ask, out: Console, question: str, suffixes: tuple[str, ...], wrong: str) -> Path:
    while True:
        src = _clean_path(ask(question))
        if not src.is_file():
            out.print(f"[red]File not found:[/red] {escape(str(src))}", highlight=False)
        elif src.suffix.lower() not in suffixes:
            out.print(wrong)
        else:
            return src


def _copy(src: Path, dest: Path) -> None:
    if not (dest.exists() and src.samefile(dest)):
        shutil.copy2(src, dest)


def _register(conn, file: Path, text_file: Path | None) -> None:
    existing = next((r for r in resumes.list_resumes(conn)
                     if r["name"].strip().lower() == MASTER_RESUME_NAME.lower()), None)
    if existing:
        resumes.update_resume(conn, existing["id"], file, text_file=text_file)
    else:
        resumes.add_resume(conn, file, MASTER_RESUME_NAME, text_file=text_file)


def run_resume_step(conn, ask: Callable[..., str] | None = None, *, console: Console | None = None) -> None:
    """Step 1: one resume file (.txt or .pdf), local PDF text extraction, confirmation, registration."""
    out = console or globals()["console"]
    if ask is None:
        def ask(question: str, **kwargs) -> str:
            return Prompt.ask(escape(question), console=out, **kwargs)

    out.print(Panel("[bold]Step 1: Resume[/bold]\nPoint to your master resume file (.txt or .pdf)."))
    while True:
        src = _ask_file(ask, out, "Resume file path", (".txt", ".pdf"),
                        "[red]Unsupported format.[/red] Provide a .txt or .pdf file.")
        txt_source: Path | None = src
        extracted: str | None = None
        pdf_source: Path | None = None
        if src.suffix.lower() == ".pdf":
            text = extract_pdf_text(src)
            if len(text) >= MIN_TEXT_CHARS:
                txt_source, extracted, pdf_source = None, text, src
            else:
                out.print(f"Could not read any text from {escape(src.name)}. It may be a scanned image, "
                          "password-protected, or damaged. Please give a plain-text (.txt) version of "
                          "your resume instead.", highlight=False)
                txt_source = _ask_file(ask, out, "Resume .txt file path", (".txt",),
                                       "Please provide a .txt file.")

        txt_path = config.RESUME_PATH
        replace = True
        if txt_path.exists() and _is_user_supplied_txt():
            replace = str(ask("resume.txt already exists. Overwrite it? [y/N]")).strip().lower() in ("y", "yes")
        if replace:
            if extracted is not None:
                txt_path.write_bytes(extracted.encode("utf-8", errors="replace"))
                _marker().write_text(_sha256(txt_path), encoding="utf-8")
            else:
                _copy(txt_source, txt_path)
                _marker().unlink(missing_ok=True)
        if pdf_source is not None:
            _copy(pdf_source, config.RESUME_PDF_PATH)

        shown = txt_path.read_text(encoding="utf-8", errors="replace")
        out.print("\nFirst lines of your resume:")
        for line in [ln for ln in shown.splitlines() if ln.strip()][:10]:
            out.print(escape(line[:100]), highlight=False)
        out.print(f"Characters read: {len(shown)}", highlight=False)
        out.print(f"Saved as {escape(str(txt_path))} (you can edit this file).", highlight=False)
        if str(ask("Does this look right? [Y/n]")).strip().lower() not in ("n", "no"):
            break

    if pdf_source is not None:
        _register(conn, config.RESUME_PDF_PATH, txt_path)
    else:
        _register(conn, txt_path, None)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

_PROPOSAL_FIELDS = {
    "contact": ("full_name", "email", "phone", "linkedin_url"),
    "location": ("city", "province_state", "country"),
}


def _resume_proposals() -> dict[str, str]:
    """Question text -> value found in resume.txt (empty when it is missing or unreadable)."""
    try:
        text = config.RESUME_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    found = propose_profile(text)
    result: dict[str, str] = {}
    for group in PROFILE_GROUPS:
        for question, field in zip(group.questions, _PROPOSAL_FIELDS.get(group.key, ())):
            if field in found:
                result[question] = found[field]
    return result


def run_profile_step(conn, ask: Callable[..., str] | None = None, *, console: Console | None = None) -> dict:
    """Ask the ten profile groups, store each reply in the answer bank, write profile.json.

    A blank reply re-asks (EEO questions store "decline to answer" instead). On a re-run, a group
    whose questions are all stored is kept unless the user answers ``n`` to the keep prompt.
    """
    out = console or globals()["console"]
    if ask is None:
        def ask(question: str, **kwargs) -> str:
            return Prompt.ask(escape(question), console=out, **kwargs)

    out.print(Panel("[bold]Step 2: Profile[/bold]\nTell HireEmber about yourself. "
                    "This powers scoring, tailoring, and auto-fill. "
                    "Never enter passwords, tokens or payment details."))
    proposals = _resume_proposals()
    total = len(PROFILE_GROUPS)
    for number, group in enumerate(PROFILE_GROUPS, 1):
        out.print(f"\n[bold cyan]Profile step {number} of {total}: {group.title}[/bold cyan]",
                  highlight=False)
        if group_complete(conn, group) and str(
                ask(f"Keep your {group.title} answers? [Y/n]")).strip().lower() not in ("n", "no"):
            continue
        if group.optional:
            out.print("[dim]Optional. Type skip or decline to leave a question unanswered.[/dim]")
        for question in group.questions:
            while True:
                default = proposals.get(question)
                if default is not None and stored_answer(conn, question) is None:
                    reply = str(ask(question, default=default)).strip()
                else:
                    reply = str(ask(question)).strip()
                if reply:
                    break
                if group.optional:
                    reply = "decline to answer"
                    break
                out.print("[yellow]An answer is needed here.[/yellow]")
            answers.save_answer(conn, question, reply, source="profile")

    profile = build_profile(conn)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    out.print(f"\n[green]Profile saved to {PROFILE_PATH}[/green]")
    return profile


# ---------------------------------------------------------------------------
# Search config
# ---------------------------------------------------------------------------

def _setup_searches() -> None:
    """Generate a searches.yaml from user input."""
    console.print(Panel("[bold]Step 3: Job Search Config[/bold]\nDefine what you're looking for."))

    location = Prompt.ask("Target location (e.g. 'Remote', 'Canada', 'New York, NY')", default="Remote")
    distance_str = Prompt.ask("Search radius in miles (0 for remote-only)", default="0")
    try:
        distance = int(distance_str)
    except ValueError:
        distance = 0

    roles_raw = Prompt.ask(
        "Target job titles (comma-separated, e.g. 'Backend Engineer, Full Stack Developer')"
    )
    roles = [r.strip() for r in roles_raw.split(",") if r.strip()]

    if not roles:
        console.print("[yellow]No roles provided. Using a default set.[/yellow]")
        roles = ["Software Engineer"]

    # Build YAML content
    lines = [
        "# HireEmber search configuration",
        "# Edit this file to refine your job search queries.",
        "",
        "defaults:",
        f'  location: "{location}"',
        f"  distance: {distance}",
        "  hours_old: 72",
        "  results_per_site: 50",
        "",
        "locations:",
        f'  - location: "{location}"',
        f"    remote: {str(distance == 0).lower()}",
        "",
        "queries:",
    ]
    for i, role in enumerate(roles):
        lines.append(f'  - query: "{role}"')
        lines.append(f"    tier: {min(i + 1, 3)}")

    SEARCH_CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Search config saved to {SEARCH_CONFIG_PATH}[/green]")


# ---------------------------------------------------------------------------
# AI Features
# ---------------------------------------------------------------------------

def _setup_ai_features() -> None:
    """Ask about AI scoring/tailoring — optional LLM configuration."""
    console.print(Panel(
        "[bold]Step 4: AI Features (optional)[/bold]\n"
        "An LLM powers job scoring, resume tailoring, and cover letters.\n"
        "Without this, you can still discover and enrich jobs."
    ))

    if not Confirm.ask("Enable AI scoring and resume tailoring?", default=True):
        console.print("[dim]Discovery-only mode. You can configure AI later with [bold]hireember init[/bold].[/dim]")
        return

    console.print("Supported providers: [bold]Gemini[/bold] (recommended, free tier), OpenAI, local (Ollama/llama.cpp)")
    provider = Prompt.ask(
        "Provider",
        choices=["gemini", "openai", "local"],
        default="gemini",
    )

    env_lines = ["# HireEmber configuration", ""]

    if provider == "gemini":
        api_key = Prompt.ask("Gemini API key (from aistudio.google.com)")
        model = Prompt.ask("Model", default="gemini-2.0-flash")
        env_lines.append(f"GEMINI_API_KEY={api_key}")
        env_lines.append(f"LLM_MODEL={model}")
    elif provider == "openai":
        api_key = Prompt.ask("OpenAI API key")
        model = Prompt.ask("Model", default="gpt-4o-mini")
        env_lines.append(f"OPENAI_API_KEY={api_key}")
        env_lines.append(f"LLM_MODEL={model}")
    elif provider == "local":
        url = Prompt.ask("Local LLM endpoint URL", default="http://localhost:8080/v1")
        model = Prompt.ask("Model name", default="local-model")
        env_lines.append(f"LLM_URL={url}")
        env_lines.append(f"LLM_MODEL={model}")

    env_lines.append("")
    ENV_PATH.write_text("\n".join(env_lines), encoding="utf-8")
    console.print(f"[green]AI configuration saved to {ENV_PATH}[/green]")


# ---------------------------------------------------------------------------
# Auto-Apply
# ---------------------------------------------------------------------------

def _setup_auto_apply() -> None:
    """Configure autonomous job application (requires Claude Code CLI)."""
    console.print(Panel(
        "[bold]Step 5: Auto-Apply (optional)[/bold]\n"
        "HireEmber can autonomously fill and submit job applications\n"
        "using Claude Code as the browser agent."
    ))

    if not Confirm.ask("Enable autonomous job applications?", default=True):
        console.print("[dim]You can apply manually using the tailored resumes HireEmber generates.[/dim]")
        return

    # Check for Claude Code CLI
    if shutil.which("claude"):
        console.print("[green]Claude Code CLI detected.[/green]")
    else:
        console.print(
            "[yellow]Claude Code CLI not found on PATH.[/yellow]\n"
            "Install it from: [bold]https://claude.ai/code[/bold]\n"
            "Auto-apply won't work until Claude Code is installed."
        )


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the full interactive setup wizard."""
    console.print()
    console.print(
        Panel.fit(
            "[bold green]HireEmber Setup Wizard[/bold green]\n\n"
            "This will create your configuration at:\n"
            f"  [cyan]{APP_DIR}[/cyan]\n\n"
            "You can re-run this anytime with [bold]hireember init[/bold].",
            border_style="green",
        )
    )

    ensure_dirs()
    console.print(f"[dim]Created {APP_DIR}[/dim]\n")

    conn = init_db()

    # Step 1: Resume
    run_resume_step(conn)
    console.print()

    # Step 2: Profile (ten groups, stored in the answer bank)
    run_profile_step(conn)
    console.print()

    # Step 3: Search config
    _setup_searches()
    console.print()

    # Step 4: AI features (optional LLM)
    _setup_ai_features()
    console.print()

    # Step 5: Auto-apply (Claude Code detection)
    _setup_auto_apply()
    console.print()

    # Done — show tier status
    from hireember.config import get_tier, TIER_LABELS, TIER_COMMANDS

    tier = get_tier()

    tier_lines: list[str] = []
    for t in range(1, 4):
        label = TIER_LABELS[t]
        cmds = ", ".join(f"[bold]{c}[/bold]" for c in TIER_COMMANDS[t])
        if t <= tier:
            tier_lines.append(f"  [green]✓ Tier {t} — {label}[/green]  ({cmds})")
        elif t == tier + 1:
            tier_lines.append(f"  [yellow]→ Tier {t} — {label}[/yellow]  ({cmds})")
        else:
            tier_lines.append(f"  [dim]✗ Tier {t} — {label}  ({cmds})[/dim]")

    unlock_hint = ""
    if tier == 1:
        unlock_hint = "\n[dim]To unlock Tier 2: configure an LLM API key (re-run [bold]hireember init[/bold]).[/dim]"
    elif tier == 2:
        unlock_hint = "\n[dim]To unlock Tier 3: install Claude Code CLI + Chrome.[/dim]"

    console.print(
        Panel.fit(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[bold]Your tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]\n\n"
            + "\n".join(tier_lines)
            + unlock_hint,
            border_style="green",
        )
    )
