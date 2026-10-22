"""Settings check run before ``hireember run`` and ``hireember apply``.

``find_needs`` lists what the requested work still lacks (models, resume, profile, search config,
browser, tools). ``run_preflight`` prints one message, offers to fix what can be fixed by asking
the same questions as ``hireember init``, and decides which stages may still run. The check makes
no LLM call and never prints API keys.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import yaml
from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt

from hireember import config, doctor, models

STAGE_ORDER = ("discover", "enrich", "score", "tailor", "cover", "pdf")
_NEED_ORDER = ("search_config", "jobspy", "fast_tier", "quality_tier", "resume", "profile",
               "browser", "claude", "chrome", "tailored")
_LLM_STAGES = {"fast_tier": ("discover", "enrich", "score"), "quality_tier": ("tailor", "cover")}
_REASONS = {
    "search_config": "search config is missing",
    "jobspy": "python-jobspy is not installed",
    "fast_tier": "fast model is not set up",
    "quality_tier": "quality model is not set up",
    "resume": "base resume is missing",
    "profile": "profile is missing",
    "browser": "Playwright browser is not installed",
}


@dataclass(frozen=True)
class Need:
    key: str
    title: str
    stages: tuple[str, ...]
    fix: str
    fixable: bool
    detail: str


@dataclass
class PreflightOutcome:
    proceed: bool
    stages: list[str]
    skipped: dict[str, str] = field(default_factory=dict)
    missing: list[Need] = field(default_factory=list)


def is_interactive() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def ask_user(question: str, **kwargs) -> str:
    """Prompt function used for every question of the check (tests patch it)."""
    return Prompt.ask(escape(question), **kwargs)


# -- detection ----------------------------------------------------------------------------------

def _expand(stages: list[str]) -> list[str]:
    if "all" in stages:
        return list(STAGE_ORDER)
    return [s for s in STAGE_ORDER if s in stages]


def _load_search_cfg() -> dict | None:
    """The search config as a mapping, or None when the file is absent or unusable."""
    path = config.SEARCH_CONFIG_PATH
    if not path.exists():
        return None
    try:
        return doctor._load_yaml_mapping(path)
    except (yaml.YAMLError, OSError, ValueError):
        return {}


def _has_career_sites() -> bool:
    try:
        sites = doctor._load_yaml_mapping(config.CONFIG_DIR / "sites.yaml").get("sites") or []
    except (yaml.YAMLError, OSError, ValueError):
        return False
    return isinstance(sites, list) and bool(sites)


def _wants_jobspy(cfg: dict) -> bool:
    try:
        return bool(config.resolve_jobspy_sites(cfg.get("sites")))
    except ValueError:
        return False


def find_needs(command: str, stages: list[str], *, conn=None, gen_url: bool = False,
               probe: bool = True) -> tuple[list[Need], list[str]]:
    """Return (missing needs in fixed order, warning lines) for the command and stages."""
    users: dict[str, list[str]] = {}

    def want(key: str, stage: str) -> None:
        if stage not in users.setdefault(key, []):
            users[key].append(stage)

    if command == "apply":
        for key in ("profile", "claude", "chrome") + (() if gen_url else ("tailored",)):
            want(key, "apply")
    else:
        for stage in _expand(stages):
            if stage == "discover":
                want("search_config", stage)
                cfg = _load_search_cfg()
                if cfg is not None and _wants_jobspy(cfg):
                    want("jobspy", stage)
                if _has_career_sites():
                    want("browser", stage)
            elif stage == "enrich":
                want("browser", stage)
            elif stage == "score":
                for key in ("fast_tier", "resume", "profile"):
                    want(key, stage)
            elif stage in ("tailor", "cover"):
                for key in ("quality_tier", "resume", "profile"):
                    want(key, stage)

    needs: list[Need] = []
    warnings: list[str] = []

    def add(key, title, fix, fixable, detail):
        needs.append(Need(key, title, tuple(users[key]), fix, fixable, detail))

    for key in _NEED_ORDER:
        if key not in users:
            continue
        if key == "search_config":
            if not config.SEARCH_CONFIG_PATH.exists():
                add(key, "Search config", "hireember init", True, "No search config (searches.yaml) found.")
        elif key == "jobspy":
            if doctor._check_jobspy().status != "OK":
                add(key, "python-jobspy", f"{sys.executable} -m pip install -e .", False,
                    "The job board scraper is not importable.")
        elif key in ("fast_tier", "quality_tier"):
            tier = key.split("_")[0]
            title = f"{tier.capitalize()} model"
            try:
                settings = models.resolve_tier(tier)
            except models.ModelsError as e:
                add(key, title, f"hireember models set {tier}", True, str(e))
                continue
            # Environment variables alone are fine (legacy setup). Once models.toml configures
            # any tier, each tier needs its own settings there.
            if settings.source == "environment" and models.load_models_file():
                add(key, title, f"hireember models set {tier}", True,
                    f"{tier} tier is not configured in models.toml. Run 'hireember models set {tier}'.")
                continue
            if probe:
                result = models.probe_tier(tier)
                if not result.ok:
                    warnings.append(f"{title} ({settings.provider} / {settings.model}) is not reachable: "
                                    f"{result.message}")
        elif key == "resume":
            from hireember import database, resumes

            c = conn if conn is not None else database.get_connection()
            if not resumes.list_resumes(c) or not config.RESUME_PATH.exists():
                add(key, "Base resume", "hireember resume add <file> --name <name>", True,
                    "No base resume is registered, or its text file is missing.")
        elif key == "profile":
            if not config.PROFILE_PATH.exists():
                add(key, "Profile", "hireember init", True, "No profile found (profile.json).")
        elif key == "browser":
            if doctor.chromium_path() is None:
                add(key, "Playwright browser", "playwright install chromium", True,
                    "The Playwright Chromium browser is not installed.")
        elif key == "claude":
            check = doctor.check_claude()
            if check.status != "OK":
                add(key, "Claude Code CLI", check.note, False, "Claude Code is needed for auto-apply.")
        elif key == "chrome":
            check = doctor.check_chrome()
            if check.status != "OK":
                add(key, "Chrome", check.note, False, "Chrome is needed for auto-apply.")
        elif key == "tailored":
            from hireember import database

            c = conn if conn is not None else database.get_connection()
            ready = c.execute(
                "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
            ).fetchone()[0]
            if ready == 0:
                add(key, "Tailored resumes", "hireember run score tailor", False,
                    "No tailored resumes ready. Run hireember run score tailor first.")
    return needs, warnings


# -- report -------------------------------------------------------------------------------------

def format_report(needs: list[Need], warnings: list[str], *, interactive: bool) -> str:
    n = len(needs)
    noun = "1 thing needs" if n == 1 else f"{n} things need"
    lines = [f"Before this run can start, {noun} setting up:", ""]
    for i, need in enumerate(needs, 1):
        lines.append(f"  {i}. {need.title} (used by {', '.join(need.stages)})")
        lines.append(f"     {need.detail}")
        lines.append(f"     Fix: {need.fix}")
    for w in warnings:
        lines.append("")
        lines.append(f"Note: {w}")
    if not interactive:
        lines.append("")
        lines.append("Run again after fixing these, or run in a terminal to be prompted.")
    return "\n".join(lines)


def skip_notes(skipped: dict[str, str]) -> list[str]:
    """One ``Skipping a, b: reason.`` line per distinct reason, stages in canonical order."""
    groups: dict[str, list[str]] = {}
    for stage in STAGE_ORDER:
        if stage in skipped:
            groups.setdefault(skipped[stage], []).append(stage)
    return [f"Skipping {', '.join(stages)}: {reason}." for reason, stages in groups.items()]


# -- fixing -------------------------------------------------------------------------------------

class _Declined(Exception):
    """The user declined a fix; ``abort`` means decline everything that remains."""

    def __init__(self, abort: bool = False):
        super().__init__()
        self.abort = abort


_LOOPING = ("Provider (gemini/openai/custom)", "Resume file path", "Resume .txt file path")


class _Asker:
    """Wraps ``ask_user``: EOF/Ctrl-C abort, and an empty or invalid answer given twice declines."""

    def __init__(self):
        self.empty: set[str] = set()
        self.counts: dict[str, int] = {}

    def __call__(self, question: str, **kwargs) -> str:
        self.counts[question] = self.counts.get(question, 0) + 1
        if question in _LOOPING and self.counts[question] > 2:
            raise _Declined()
        try:
            reply = ask_user(question, **kwargs)
        except (EOFError, KeyboardInterrupt):
            raise _Declined(abort=True) from None
        if not str(reply).strip() and not question.endswith("[Y/n]") and question != "API key":
            if question in self.empty:
                raise _Declined()
            self.empty.add(question)
        return reply


def _yes(asker: _Asker, question: str) -> bool:
    return str(asker(question)).strip().lower() not in ("n", "no")


def _same_as_fast(out: Console) -> bool:
    try:
        fast = models.resolve_tier("fast")
    except models.ModelsError:
        return False
    models.save_tier("quality", provider=fast.provider, model=fast.model,
                     base_url=fast.base_url if fast.provider == "custom" else None,
                     api_key=fast.api_key or None)
    out.print(f"Saved quality tier to {config.MODELS_PATH}", highlight=False, markup=False)
    return True


def _fix(need: Need, asker: _Asker, out: Console, conn) -> None:
    from hireember.wizard import init as wiz

    if need.key in ("fast_tier", "quality_tier"):
        tier = need.key.split("_")[0]
        if not _yes(asker, f"Set up the {tier} model now? [Y/n]"):
            raise _Declined()
        if tier == "quality":
            try:
                models.resolve_tier("fast")
                offer_same = True
            except models.ModelsError:
                offer_same = False
            if offer_same and _yes(asker, "Use the same settings as the fast tier? [Y/n]"):
                _same_as_fast(out)
                return
        wiz._ask_tier(asker, out, tier)
    elif need.key == "resume":
        if not _yes(asker, "Add your resume now? [Y/n]"):
            raise _Declined()
        wiz.run_resume_step(conn, asker, console=out)
    elif need.key == "profile":
        if not _yes(asker, "Run the profile step of init now? [Y/n]"):
            raise _Declined()
        wiz.run_profile_step(conn, asker, console=out)
    elif need.key == "search_config":
        if not _yes(asker, "Run the search step of init now? [Y/n]"):
            raise _Declined()
        wiz._setup_searches(asker, out)
    elif need.key == "browser":
        if not _yes(asker, "Install the Playwright browser now (playwright install chromium)? [Y/n]"):
            raise _Declined()
        wiz.offer_chromium_install(lambda q, **k: "y", console=out)


def _decide(command: str, stages: list[str], missing: list[Need]) -> PreflightOutcome:
    """Apply the stage-skipping rule to what is still missing."""
    from hireember.pipeline import _UPSTREAM

    if command == "apply":
        return PreflightOutcome(proceed=not missing, stages=[], missing=missing)
    requested = _expand(stages)
    skipped: dict[str, str] = {}
    for stage in requested:
        for need in missing:
            if stage in need.stages and need.key in _REASONS:
                skipped[stage] = _REASONS[need.key]
                break
        else:
            upstream = _UPSTREAM.get(stage)
            if upstream in skipped:
                skipped[stage] = skipped[upstream]
    run = [s for s in requested if s not in skipped]
    return PreflightOutcome(proceed=bool(run), stages=run, skipped=skipped, missing=missing)


def run_preflight(command: str, stages: list[str], *, no_prompt: bool = False, gen_url: bool = False,
                  console: Console | None = None) -> PreflightOutcome:
    out = console or Console()
    conn = None
    if command == "apply" or any(s in ("all", "score", "tailor", "cover") for s in stages):
        from hireember import database

        conn = database.get_connection()
    needs, warnings = find_needs(command, stages, conn=conn, gen_url=gen_url)
    requested = [] if command == "apply" else _expand(stages)
    if not needs:
        return PreflightOutcome(proceed=True, stages=requested)

    interactive = is_interactive() and not no_prompt
    out.print(format_report(needs, warnings, interactive=interactive), markup=False, highlight=False,
              soft_wrap=True)
    if not interactive:
        return PreflightOutcome(proceed=False, stages=[], missing=needs)

    asker = _Asker()
    aborted = False
    for need in needs:
        if aborted or not need.fixable:
            continue
        out.print()
        try:
            _fix(need, asker, out, conn)
        except _Declined as d:
            aborted = d.abort
            continue
        except KeyboardInterrupt:
            aborted = True
            continue
        remaining, _ = find_needs(command, stages, conn=conn, gen_url=gen_url, probe=False)
        if need.key not in {n.key for n in remaining}:
            out.print(f"{need.title}: set.", markup=False, highlight=False)

    missing, _ = find_needs(command, stages, conn=conn, gen_url=gen_url, probe=False)
    if not missing:
        out.print("All set. Starting run.", markup=False, highlight=False)
        return PreflightOutcome(proceed=True, stages=requested)

    outcome = _decide(command, stages, missing)
    if outcome.proceed:
        for note in skip_notes(outcome.skipped):
            out.print(note, markup=False, highlight=False, soft_wrap=True)
    else:
        outcome.stages = []
        names = ", ".join(n.title for n in missing)
        out.print(f"Still missing: {names}.", markup=False, highlight=False, soft_wrap=True)
    return outcome
