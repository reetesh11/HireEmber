# Interface contract — phase-3-apply-rework

All paths are under `src/hireember/`. Import examples use the package name `hireember`.

### Constants (`hireember.apply.session`)

```python
REASON_ACCOUNT = "account needed"
REASON_CAPTCHA = "captcha"
REASON_IDENTITY = "identity check"
REASON_VIDEO = "video or biometric"
REASON_REVIEW = "review before submit"
REASON_MANUAL = "manual site"
REASON_OUTCOME = "outcome unknown"
REASON_RECOVERED = "recovered after interrupted run"
REASON_NO_RESULT = "agent finished without a result"
REASON_CLOSED_DEFAULT = "closed by employer page"
STOP_REASONS = (REASON_ACCOUNT, REASON_CAPTCHA, REASON_IDENTITY, REASON_VIDEO)
INJECTION_LOG_KIND = "injected instruction ignored"
```

Queue item `kind` and ticket `status_reason` are the same string for every stop. For questions they are the existing `hireember.answers` constants: `KIND_UNKNOWN = "unknown question"`, `KIND_CONFLICT = "conflicting answers"`, `KIND_SENSITIVE = "sensitive question"`. (This replaces the shorter words `unknown`, `conflict`, `sensitive` in the product spec's AC-1; the existing constants win because phases 1 and 2 already store them.) New item kinds: `account needed`, `captcha`, `identity check`, `video or biometric`, `review before submit`, `manual site`, `outcome unknown`.

### `hireember.apply.session`

```python
@dataclass
class FieldDecision:
    action: str            # "fill" or "stop"
    value: str | None      # text to type when action == "fill"
    source: str            # "answer:<answers.id>", "profile:<key>", or "" when action == "stop"
    reason: str            # "" when fill; else the ticket status_reason set by the stop
    queue_item_id: int | None

class GateSession:
    def __init__(self, conn: sqlite3.Connection, ticket_id: int, *,
                 review_before_submit: bool | None = None, attempt: int | None = None) -> None
    ticket_id: int
    attempt: int                      # attempt number in attempt_log
    resume_from: str | None           # page link to continue on after `queue ready`, else None
    state: str                        # "open", "blocked", "closed", "submit_pressed", "submitted"

    def answer_field(self, question: str, field_type: str = "text") -> FieldDecision
    def resume_path(self) -> str
    def stop(self, reason: str, page_link: str = "") -> None
    def note_page_text(self, text: str) -> bool
    def before_submit(self) -> str
    def submit_pressed(self) -> None
    def submitted(self, confirmation_link: str | None = None) -> None
    def closed(self, reason: str = "") -> None
```

- `answer_field(question, field_type)`: `field_type` is the HTML-like type (`text`, `textarea`, `select`, `radio`, `checkbox`, `file`, `password`, `email`, `tel`). A field of type `password`, or a question for which `answers.is_sensitive(question)` is true, never gets a value: the ticket becomes `blocked for human` with reason `sensitive question`, one open queue item of kind `sensitive question` is created (reused if the same question is already open) and the decision is `FieldDecision("stop", None, "", "sensitive question", item_id)`. Otherwise a profile match (full name, email, phone, from `config.load_profile()`; map in `session._PROFILE_FIELDS`) is tried first, then `answers.match_answer`. A bank hit fills with source `answer:<id>` and increments `times_used` once. No bank entry blocks with `unknown question`; two differing entries block with `conflicting answers`. Every call writes an `attempt_log` row (`kind` `fill` or `stop`, `field` = the question, `source`). A filled value is logged in `detail`; a stopped one never is.
- `resume_path()` returns the absolute path of the ticket's tailored resume PDF (`tickets.tailored_resume_path` with suffix `.pdf`) and logs kind `upload`, `field` = file name. Raises `SessionError("No tailored resume for ticket <id>.")` if none.
- `stop(reason, page_link)`: `reason` must be one of `STOP_REASONS` else `ValueError`. Sets the ticket `blocked for human` with that reason (actor `system`), creates a queue item with `kind = reason`, `reason = reason`, `page_link = page_link`, `question_text = <company name>`, keeps `session_link` on the ticket, logs kind `stop`, sets `state = "blocked"`.
- `note_page_text(text)`: returns `True` and writes an `attempt_log` row `kind = "injected instruction ignored"`, `detail = <the matching sentence>` when the text matches an instruction pattern (for example "ignore previous instructions", "disregard", "you must now", "system prompt", "act as"); otherwise `False`. It never changes ticket state or any answer.
- `before_submit()` returns `"submit"`, or `"stop"` when review is on. With review on it blocks the ticket (`review before submit`, queue kind `review before submit`, `page_link` empty) and sets `state = "blocked"`. Review is on when the constructor argument is `True`, or is `None` and the setting `review_before_submit` is `"true"`.
- `submit_pressed()`: must be called before the agent clicks submit. Sets `tickets.submitted_at` (UTC ISO) and `state = "submit_pressed"`; logs kind `submit`.
- `submitted(confirmation_link)`: sets the ticket `applied` (actor `system`), `tickets.confirmation_link` to the link when given; if `None` or blank sets `tickets.unverified = 1`. Clears `session_link` and `resume_link`. Calls `limits.record_submission`. `state = "submitted"`. Calling it without a prior `submit_pressed()` sets `submitted_at` itself.
- `closed(reason)`: ticket becomes `closed` with `reason` (or `REASON_CLOSED_DEFAULT` when blank), no queue item, `state = "closed"`.
- `resume_from`: set at construction to `tickets.resume_link` when the ticket has one (written by `queue ready`); the constructor logs kind `resume`, `detail` = that link.
- `SessionError(Exception)` is raised for misuse (unknown ticket, `stop` after `closed`).

### `hireember.apply.runner`

```python
@dataclass
class ApplyOutcome:
    ticket_id: int
    result: str      # "applied", "blocked", "closed", "held", "duplicate", "interrupted", "skipped"
    reason: str      # status_reason of the ticket after the attempt
    session: GateSession | None

def apply_ticket(conn: sqlite3.Connection, ticket_id: int,
                 agent: Callable[[GateSession], None], *,
                 review_before_submit: bool | None = None,
                 now: datetime | None = None,
                 session_link: str = "http://127.0.0.1:9222") -> ApplyOutcome

def recover_stale_tickets(conn: sqlite3.Connection) -> list[int]
```

`apply_ticket` order of work (the agent is called only if every check passes):
1. Ticket status `applied` or `closed`, or `blocked for human` with reason other than `ready`: return `skipped`, agent not called.
2. Company flagged manual-only (`tickets.is_manual_company`): ticket `blocked for human`, reason `manual site`, one queue item kind `manual site`; return `blocked`. Agent not called.
3. If status is `pending`: `tickets.set_status(..., "started")`. A `DuplicateTicketError` returns `duplicate` with the ticket `blocked for human`, reason `duplicate`; agent not called.
4. `limits.check_limits(conn, ticket_id, now)`; if not ok, `limits.hold_ticket`; return `held`; agent not called. Status goes back to or stays `pending`.
5. `tickets.set_status(..., "applying", link=session_link, link_kind="session")`, `tickets.session_link = session_link`, `attempts.start_attempt`, build `GateSession`, call `agent(session)`.
6. After the agent returns: `session.state` of `submitted` gives `applied`; `blocked` gives `blocked`; `closed` gives `closed`. Any other state: if `submit_pressed` was called, block with `outcome unknown` (queue kind `outcome unknown`); else set `pending` with reason `agent finished without a result` and return `interrupted`.
7. If the agent raises any exception (including `KeyboardInterrupt`): log kind `error`; if `submit_pressed` was called, the ticket is `blocked for human` with reason `outcome unknown` plus a queue item; otherwise it returns to `pending` with reason `interrupted before submit`. The exception is re-raised only if it is not an `Exception` subclass.

`recover_stale_tickets(conn)`: for every ticket in status `applying`: if `submitted_at` is set, move to `blocked for human`, reason `outcome unknown`, queue item kind `outcome unknown`; else move to `pending`, reason `recovered after interrupted run`. Actor `system`. Returns the recovered ticket ids. Called at the start of `launcher.main`.

### `hireember.apply.limits`

Settings keys (integer strings in the `settings` table): `max_open_per_company`, `max_per_day`, `company_wait_hours`.

```python
DEFAULT_MAX_OPEN_PER_COMPANY = 3
DEFAULT_MAX_PER_DAY = 25
DEFAULT_COMPANY_WAIT_HOURS = 24

@dataclass
class LimitResult:
    ok: bool
    reason: str               # "" when ok; else starts with "limit: company", "limit: daily"
    not_before: str | None    # UTC ISO time the ticket becomes eligible, or None

def check_limits(conn, ticket_id: int, now: datetime | None = None) -> LimitResult
def hold_ticket(conn, ticket_id: int, result: LimitResult) -> None
def record_submission(conn, ticket_id: int, now: datetime | None = None) -> None
def eligible_ticket_ids(conn, now: datetime | None = None) -> list[int]
```

- Open applications for a company are tickets of the same company (the `tickets._COMPANY` expression) in `started`, `applying` or `blocked for human`, excluding this ticket. If that count is at least `max_open_per_company`: `LimitResult(False, "limit: company (<n> open)", None)`.
- If any other ticket of the same company has `submitted_at` within the last `company_wait_hours`: `LimitResult(False, "limit: company wait until <YYYY-MM-DD HH:MM>", <submitted_at + wait, UTC ISO>)`.
- If tickets with `submitted_at` on the same UTC date as `now` number at least `max_per_day`: `LimitResult(False, "limit: daily", <next UTC midnight ISO>)`.
- Checks run in that order; the first failing one is returned.
- `hold_ticket` keeps the ticket `pending`, writes `status_reason = result.reason` and `not_before`, adds one history event (actor `system`) only when the reason changes.
- `record_submission` sets `not_before` and the reason `limit: company wait until …` on every other `pending` ticket of the same company.
- `eligible_ticket_ids` returns `pending` ticket ids with `not_before` null or at or before `now`, ordered by score descending then id.

### `hireember.apply.attempts`

```python
def start_attempt(conn, ticket_id: int) -> int           # next attempt number for the ticket, starting at 1
def log_step(conn, ticket_id: int, attempt: int, kind: str, field: str = "",
             source: str = "", detail: str = "") -> None
def get_log(conn, ticket_id: int) -> list[dict]           # keys: id, attempt, time, kind, field, source, detail; oldest first
```

`kind` values written: `start`, `fill`, `stop`, `upload`, `submit`, `resume`, `error`, `injected instruction ignored`.

### `hireember.tickets` additions

```python
class CompanyNotFoundError(TicketError)       # message: No company named "<name>".
def get_setting(conn, key: str, default: str | None = None) -> str | None
def set_company_manual(conn, name: str, manual: bool = True) -> int        # returns companies.id; raises CompanyNotFoundError
def is_manual_company(conn, ticket_id: int) -> bool
def list_companies(conn) -> list[dict]        # keys: id, name, manual_only (bool); ordered by name
def set_reason(conn, ticket_id: int, reason: str, *, actor: str = "system",
               not_before: str | None = None) -> None
```

`set_reason` rewrites `status_reason` (and `not_before`) without changing status and without a history event if the reason is unchanged. Company matching in `set_company_manual` is case-insensitive and trimmed, like `get_or_create_company`. `is_manual_company` looks up the company of the ticket's job (`jobs.company_id`, else the company whose name equals `jobs.site`); it is `False` when none.

### `hireember.answers` changes

- `AnswerResult` gains `answer_id: int | None = None` (last field, default `None`); `match_answer` sets it on an `answered` result.
- `list_queue(conn, include_resolved=False)` rows gain `page_link` and `company` (company name of the ticket's job, or `""`).
- `READY_KINDS = ("account needed", "captcha", "identity check", "video or biometric", "review before submit", "manual site", "outcome unknown")`.
- `ready_queue_item(conn, item_id: int) -> QueueAnswerResult`: only for a kind in `READY_KINDS`; resolves the item; sets `tickets.resume_link = page_link` (None if empty); moves the ticket from `blocked for human` to `pending` with reason `ready`, actor `user`, clearing `not_before`. Message: `Ticket <id> is ready to resume.` Raises `QueueError` for an unknown or resolved item (`Queue item <id> not found or already resolved.`) and for a question kind (`Use "queue answer" for this item.`). For `outcome unknown` it behaves like any other ready kind: the ticket goes to `pending` with reason `ready`, `submitted_at` is cleared so the next run may apply again, and `resume_link` is left empty (the user has chosen to retry). Automatic runs still never retry an `outcome unknown` ticket; only this user action does.
- `answer_queue_item` raises `QueueError('Use "queue ready" for this item.')` for a kind in `READY_KINDS`.

### `hireember.apply.chrome` additions

```python
class DefaultProfileError(ValueError)
def assert_dedicated_profile(path: Path) -> None
def check_worker_profiles(workers: int = 1) -> None
```

`assert_dedicated_profile` raises `DefaultProfileError("Refusing to use the default Chrome profile. HireEmber uses its own browser profile.")` when the resolved path equals, is inside, or contains `config.get_chrome_user_data()`. `check_worker_profiles(n)` checks `config.CHROME_WORKER_DIR / f"worker-{i}"` for `i < n`. `launch_chrome` calls `assert_dedicated_profile` first. `setup_worker_profile` no longer clones from the user's real Chrome profile; with no other worker profile it creates an empty one.

### `hireember.apply.launcher` (public surface)

```python
def build_mcp_config(cdp_port: int, ticket_id: int) -> dict        # replaces _make_mcp_config
def agent_tools() -> list[str]                                     # ["mcp__playwright", "mcp__hireember"]
def run_job(job: dict, port: int, worker_id: int = 0, model: str = "sonnet",
            dry_run: bool = False, session: GateSession | None = None) -> tuple[str, int]
def main(limit=1, target_url=None, min_score=7, headless=False, model="sonnet", dry_run=False,
         continuous=False, poll_interval=60, workers=1, review=None) -> None
```

- `build_mcp_config(...)["mcpServers"]` has exactly the keys `playwright` and `hireember`. The `hireember` entry runs `[sys.executable, "-m", "hireember.apply.gate_server", "--ticket", str(ticket_id)]`. There is no `gmail` key anywhere.
- `run_job` passes `--allowedTools` built from `agent_tools()` and `--strict-mcp-config`. It no longer passes `--disallowedTools` for mail tools (there are none).
- `acquire_job` skips a job whose ticket is `blocked for human`, `closed`, `applied` or `applying`, or has `not_before` in the future. A job with no ticket row is still eligible and gets one through `tickets.ensure_ticket`. Unchanged signature.
- `main` calls `recover_stale_tickets` and `chrome.check_worker_profiles(workers)` before starting any worker. `review` overrides the `review_before_submit` setting for the run.
- `worker_loop` ends a job as follows: `applied` calls `mark_result(url, "applied")`; a ticket-blocked or held outcome calls `release_lock(url)`; a closed outcome calls `mark_result(url, "expired", reason, permanent=True)`; other failures call `mark_result(url, "failed", ...)` as today.

### `hireember.apply.gate_server`

```python
TOOLS: list[dict]                      # MCP tool descriptors: name, description, inputSchema
def call_tool(session: GateSession, name: str, arguments: dict) -> dict
def serve(ticket_id: int, review: bool | None = None) -> None     # stdio JSON-RPC loop
```

Tool names and arguments: `answer_field(question, field_type)`, `resume_path()`, `stop(reason, page_link)`, `page_text(text)`, `before_submit()`, `submit_pressed()`, `submitted(confirmation_link)`, `closed(reason)`. `call_tool` returns a JSON-serializable dict (`FieldDecision` as `{"action","value","source","reason"}`, `before_submit` as `{"action": "submit" | "stop"}`, others `{"ok": true}`); an unknown tool name raises `ValueError`. Run as `python -m hireember.apply.gate_server --ticket N [--review]`.

### `hireember.apply.prompt`

`build_prompt(job: dict, tailored_resume: str, cover_letter: str | None = None, dry_run: bool = False) -> str` keeps its signature. The text it returns, compared case-insensitively, contains none of: `capsolver`, `gmail`, `send_email`, `search_emails`, `read_email`, `verification code`, `sign up`, `signup`, `create an account`, `create account`. It contains the strings `answer_field`, `stop`, `before_submit`, `submit_pressed`, `submitted`, `closed`. The module no longer defines `_build_captcha_section` and `profile["personal"]["password"]` is never read.

### `hireember.migration` / schema

`migration.create_schema(conn)` also runs `ensure_phase3_schema(conn)` (idempotent, additive; see data changes).

### `hireember.doctor`

`run_checks()` returns 11 checks; none is named `CapSolver API key`. `doctor.py` has no `_check_capsolver`.

### CLI (`hireember.cli.app`, Typer; `CliRunner` exit codes and text)

- `hireember apply [existing options] [--review]`: `--review` turns review-before-submit on for the run. Before `check_tier` and before any Chrome or Claude start, `chrome.check_worker_profiles(workers)`; on `DefaultProfileError` it prints `Refusing to use the default Chrome profile. HireEmber uses its own browser profile.` and exits 1. The LinkedIn check stays first and still runs before the database is opened.
- `hireember queue ready ITEM_ID`: prints `ready_queue_item(...).message`; `QueueError` text printed and exit 1.
- `hireember queue list`: columns `Id`, `Ticket`, `Kind`, `Company`, `Page`, `Question`.
- `hireember company manual NAME [--off]`: prints `Company "<NAME>" is now manual-only.` or, with `--off`, `Company "<NAME>" is no longer manual-only.`; an unknown name prints `No company named "<NAME>".` and exits 1.
- `hireember company list`: table `Id`, `Name`, `Manual-only` (`yes` or `no`); with none prints `No companies yet.`
- `hireember ticket log TICKET_ID`: table `Attempt`, `Time`, `Step`, `Field`, `Source`, `Detail`; with no rows prints `No attempts logged for ticket <id>.`; an unknown ticket prints `Ticket <id> not found.` and exits 1.
- `hireember status`: the "Tickets needing attention" table gains the held `pending` tickets (reason starts with `limit:`) and shows the reason; a ticket with `not_before` shows it in the `Reason` cell (`limit: company wait until 2026-10-19 09:30`).
- `hireember init` no longer asks for a CapSolver key.
- The `cli.py` `Typer(help=...)` strings for `company_app` (`"Companies and the manual-only flag."`) and `ticket_app` (`"Ticket details."`) are set at construction (standards: help text lives there).
