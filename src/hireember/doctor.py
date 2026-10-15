"""Setup diagnostics for ``hireember doctor``.

Each check is a small function returning a :class:`Check` record, so tests
can call checks directly and the CLI only renders them.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from hireember import config

MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 18


@dataclass(frozen=True)
class Check:
    """One doctor result line. ``status`` is OK, MISSING, WARN or optional."""

    name: str
    status: str
    note: str


# -- Platform checks ---------------------------------------------------------

def check_python(version: tuple[int, int, int] | None = None) -> Check:
    """Python 3.11+ is required."""
    if version is None:
        version = tuple(sys.version_info[:3])
    text = ".".join(str(p) for p in version)
    if tuple(version[:2]) >= MIN_PYTHON:
        return Check("Python", "OK", text)
    return Check("Python", "MISSING", f"found {text}, need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+")


def check_chrome() -> Check:
    """Chrome/Chromium is needed for auto-apply."""
    try:
        path = config.get_chrome_path()
    except FileNotFoundError:
        return Check("Chrome/Chromium", "MISSING",
                     "Install Chrome or set CHROME_PATH env var (needed for auto-apply)")
    return Check("Chrome/Chromium", "OK", str(path))


def get_node_version() -> tuple[int, int, int] | None:
    """Return the installed Node.js version, or None if absent or unparseable."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        proc = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (proc.stdout or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def check_node() -> Check:
    """Node.js 18+ is needed for the Playwright MCP server used by auto-apply."""
    version = get_node_version()
    if version is None:
        return Check("Node.js", "MISSING", "Install Node.js 18+ from nodejs.org (needed for auto-apply)")
    text = "v" + ".".join(str(p) for p in version)
    if version[0] >= MIN_NODE_MAJOR:
        return Check("Node.js", "OK", text)
    return Check("Node.js", "MISSING", f"found {text}, need {MIN_NODE_MAJOR}+")


def check_claude() -> Check:
    """Claude Code CLI is needed for auto-apply."""
    claude_bin = shutil.which("claude")
    if claude_bin:
        return Check("Claude Code CLI", "OK", claude_bin)
    return Check("Claude Code CLI", "MISSING", "Install from https://claude.ai/code (needed for auto-apply)")


# -- Data checks -------------------------------------------------------------

def check_database(db_path: str | Path | None = None) -> Check:
    """The jobs database exists and opens read-only. Never creates the file."""
    path = Path(db_path if db_path is not None else config.DB_PATH)
    if not path.exists():
        return Check("Database", "MISSING", f"{path} not found — run 'hireember init' or 'hireember run'")
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return Check("Database", "MISSING", f"{path}: {e}")
    return Check("Database", "OK", str(path))


def check_sources(search_cfg: dict | None = None) -> Check:
    """Summarise the configured job sources (JobSpy boards, Workday, career sites)."""
    if search_cfg is None:
        search_cfg = config.load_search_config() or {}
    boards = config.resolve_jobspy_sites(search_cfg.get("sites"))

    from hireember.discovery.workday import load_employers

    employers = load_employers() or {}
    sites = config.load_sites_config().get("sites") or []

    note = (
        f"JobSpy: {', '.join(boards) if boards else 'none'} | "
        f"Workday employers: {len(employers)} | career sites: {len(sites)}"
    )
    total = len(boards) + len(employers) + len(sites)
    return Check("Job sources", "OK" if total else "MISSING", note)


# -- Existing setup checks (moved from cli.doctor) ---------------------------

def _check_profile() -> Check:
    if config.PROFILE_PATH.exists():
        return Check("profile.json", "OK", str(config.PROFILE_PATH))
    return Check("profile.json", "MISSING", "Run 'hireember init' to create")


def _check_resume() -> Check:
    if config.RESUME_PATH.exists():
        return Check("resume.txt", "OK", str(config.RESUME_PATH))
    if config.RESUME_PDF_PATH.exists():
        return Check("resume.txt", "WARN", "Only PDF found — plain-text needed for AI stages")
    return Check("resume.txt", "MISSING", "Run 'hireember init' to add your resume")


def _check_search_config() -> Check:
    if config.SEARCH_CONFIG_PATH.exists():
        return Check("searches.yaml", "OK", str(config.SEARCH_CONFIG_PATH))
    return Check("searches.yaml", "WARN", "Will use example config — run 'hireember init'")


def _check_jobspy() -> Check:
    try:
        import jobspy  # noqa: F401
    except ImportError:
        return Check("python-jobspy", "WARN",
                     "pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex")
    return Check("python-jobspy", "OK", "Job board scraping available")


def _check_llm() -> Check:
    if os.environ.get("GEMINI_API_KEY"):
        return Check("LLM API key", "OK", f"Gemini ({os.environ.get('LLM_MODEL', 'gemini-2.0-flash')})")
    if os.environ.get("OPENAI_API_KEY"):
        return Check("LLM API key", "OK", f"OpenAI ({os.environ.get('LLM_MODEL', 'gpt-4o-mini')})")
    if os.environ.get("LLM_URL"):
        return Check("LLM API key", "OK", f"Local: {os.environ.get('LLM_URL')}")
    return Check("LLM API key", "MISSING", f"Set GEMINI_API_KEY in {config.ENV_PATH} (run 'hireember init')")


def _check_capsolver() -> Check:
    if os.environ.get("CAPSOLVER_API_KEY"):
        return Check("CapSolver API key", "OK", "CAPTCHA solving enabled")
    return Check("CapSolver API key", "optional", "Set CAPSOLVER_API_KEY in .env for CAPTCHA solving")


def run_checks() -> list[Check]:
    """Run every doctor check, in display order."""
    return [
        check_python(),
        _check_profile(),
        _check_resume(),
        _check_search_config(),
        _check_jobspy(),
        _check_llm(),
        check_claude(),
        check_chrome(),
        check_node(),
        check_database(),
        check_sources(),
        _check_capsolver(),
    ]
