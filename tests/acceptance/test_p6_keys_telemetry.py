"""Phase 6 AC-3 and AC-6: no API key in tracked files or the database; no telemetry client."""

import ast
import re
import sqlite3
import subprocess
from pathlib import Path

from p6_helpers import REPO_ROOT, Recorder, make_ticket

# Built from pieces so this file does not match its own scan.
KEY_PATTERNS = (
    re.compile("sk" + "-ant" + "-"),
    re.compile("sk" + r"-[A-Za-z0-9_-]{20,}"),
    re.compile("AI" + "za" + r"[0-9A-Za-z_-]{35}"),
)


def _hits(text: str) -> list[str]:
    return [m.group(0)[:12] for p in KEY_PATTERNS for m in p.finditer(text)]


def _tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True)
    return [REPO_ROOT / n for n in out.stdout.decode("utf-8").split("\0") if n]


def _db_hits(conn: sqlite3.Connection) -> list[str]:
    found = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for table in tables:
        for row in conn.execute(f'SELECT * FROM "{table}"').fetchall():
            for value in row:
                if isinstance(value, str) and _hits(value):
                    found.append(f"{table}: {value[:20]}")
    return found


def test_scanner_patterns_match_keys_and_ignore_ordinary_text():
    assert _hits("key " + "sk" + "-ant" + "-api03-abc")
    assert _hits("sk" + "-" + "a" * 24)
    assert _hits("AI" + "za" + "B" * 35)
    assert not _hits("risk-assessment, task-list and a short sk-abc")


def test_no_tracked_file_contains_an_api_key():
    files = _tracked_files()
    assert len(files) > 50
    offenders = []
    for path in files:
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        if _hits(data.decode("utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_seeded_database_holds_no_api_key(isolated_db, monkeypatch):
    from hireember.database import init_db
    from hireember.runs import execute_run

    monkeypatch.setenv("GEMINI_API_KEY", "gem-env-value-not-for-storage-1234567")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-env-value-not-for-storage-1234567")
    conn = init_db()
    for i in range(3):
        make_ticket(conn, f"k{i}", "pending")
    execute_run("manual", stages=Recorder().stages(), conn=conn)
    assert _db_hits(conn) == []
    values = " ".join(str(v) for t in ("tickets", "jobs", "runs", "run_log")
                      for row in conn.execute(f"SELECT * FROM {t}").fetchall() for v in row)
    assert "env-value-not-for-storage" not in values


def test_database_scan_detects_a_planted_key(tmp_path):
    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", ("my key is " + "sk" + "-ant" + "-zzz",))
    assert _db_hits(conn) != []


def test_env_is_git_ignored_and_env_example_is_not():
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT)
    assert ignored.returncode == 0
    example = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=REPO_ROOT)
    assert example.returncode != 0
    assert REPO_ROOT.joinpath(".env.example").is_file()
    tracked = {p.name for p in _tracked_files()}
    assert ".env.example" in tracked and ".env" not in tracked


# -- AC-6: no telemetry ------------------------------------------------------------

TELEMETRY_MODULES = ("sentry_sdk", "posthog", "segment", "analytics", "mixpanel", "amplitude",
                     "opentelemetry", "datadog", "ddtrace", "newrelic", "rollbar", "bugsnag")
TELEMETRY_HOSTS = ("sentry.io", "posthog.com", "segment.io", "segment.com", "mixpanel.com",
                   "amplitude.com", "datadoghq.com", "google-analytics.com", "rollbar.com",
                   "bugsnag.com", "newrelic.com", "plausible.io")


def _imported_roots(tree: ast.AST) -> set[str]:
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_telemetry_client_is_imported_or_called_in_the_package():
    src = REPO_ROOT / "src" / "hireember"
    files = list(src.rglob("*.py"))
    assert len(files) > 20
    offenders = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        bad = _imported_roots(ast.parse(text)) & set(TELEMETRY_MODULES)
        bad |= {h for h in TELEMETRY_HOSTS if h in text}
        if bad:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(bad)}")
    assert offenders == []


def test_pyproject_lists_no_telemetry_dependency():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert len(text) > 100
    found = [m for m in TELEMETRY_MODULES + ("sentry-sdk", "python-posthog") if re.search(
        r'["\']' + re.escape(m) + r"[\"'<>=!~\[ ;]", text)]
    assert found == []

