"""Local-only HTTP server for the web dashboard (standard library, JSON API plus one page)."""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import webbrowser
from dataclasses import asdict
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from hireember import answers, database, resumes, runs, tickets
from hireember.web import queries

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY = 10 * 1024 * 1024
_INDEX = Path(__file__).parent / "static" / "index.html"
_WRITE_METHODS = ("POST", "PUT", "DELETE")


class HostRefusedError(ValueError):
    """The dashboard only binds to 127.0.0.1."""

    def __init__(self, host: str):
        super().__init__(
            f"Refusing to bind to {host}. The dashboard is local only and binds to {DEFAULT_HOST}.")


class ApiError(Exception):
    """An error with an HTTP status and a JSON body."""

    def __init__(self, status: int, message: str, code: str = "error", **extra):
        super().__init__(message)
        self.status, self.message, self.code, self.extra = status, message, code, extra


# -- request helpers --------------------------------------------------------

def _int_param(params: dict, name: str, error: str) -> int | None:
    value = (params.get(name) or [""])[0].strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ApiError(400, error, "bad_filter") from None


def _view_args(params: dict) -> tuple[queries.TicketFilters, str, str]:
    score_error = "Enter a whole number from 0 to 100."
    flt = queries.TicketFilters(
        company=(params.get("company") or [""])[0],
        score_min=_int_param(params, "score_min", score_error),
        score_max=_int_param(params, "score_max", score_error),
        date_from=(params.get("date_from") or [""])[0].strip() or None,
        date_to=(params.get("date_to") or [""])[0].strip() or None,
        resume_id=_int_param(params, "resume_id", "Choose a resume from the list."),
    )
    sort = (params.get("sort") or ["updated"])[0] or "updated"
    direction = (params.get("dir") or ["desc"])[0] or "desc"
    return flt, sort, direction


def _list(conn, params: dict) -> tuple[list[dict], tuple]:
    flt, sort, direction = _view_args(params)
    try:
        return queries.list_tickets(conn, flt, sort, direction), (flt, sort, direction)
    except ValueError as exc:
        raise ApiError(400, str(exc), "bad_filter") from None


# -- GET routes -------------------------------------------------------------

def _tickets_list(conn, params):
    rows, _ = _list(conn, params)
    blocked = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE status = 'blocked for human'").fetchone()[0]
    return {"tickets": rows, "counts": queries.status_counts(rows), "total": len(rows),
            "blocked_count": blocked}


def _ticket_detail(conn, ticket_id: int):
    base = tickets.get_ticket(conn, ticket_id)
    row = queries.get_ticket_row(conn, ticket_id) or {}
    detail = {**base, **row}
    detail["history"] = list(reversed(tickets.get_history(conn, ticket_id)))
    blocked = None
    if base["status"] == "blocked for human":
        item = queries.blocked_queue(conn, ticket_id)
        if item:
            i = item[0]
            blocked = {k: i[k] for k in ("reason", "next_step", "question", "queue_item_id")}
    detail["blocked"] = blocked
    return detail


def _blocked(conn):
    items = queries.blocked_queue(conn)
    return {"count": len(items), "items": items}


def _answers(conn):
    return {"answers": [
        {"id": a["id"], "question": a["question_text"], "answer": a["answer"],
         "source": a["source"], "last_used_at": a["last_used_at"], "times_used": a["times_used"]}
        for a in answers.list_answers(conn)]}


def _resumes(conn):
    return {"resumes": [
        {"id": r["id"], "name": r["name"], "tags": r["tags"], "pinned": r["pinned"],
         "file_name": Path(r["file_path"] or "").name}
        for r in resumes.list_resumes(conn)]}


def _text(body: dict, key: str) -> str:
    value = body.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ApiError(400, f"{key} must be text.", "bad_request")
    return value


def _id(body: dict, key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(400, f"{key} must be a whole number.", "bad_request")
    return value


def _change_status(conn, ticket_id: int, body: dict) -> dict:
    status = body.get("status")
    previous = tickets.get_ticket(conn, ticket_id)["status"]
    override = body.get("override_reason")
    tickets.set_status(conn, ticket_id, status, actor="user", reason=_text(body, "reason"),
                       override_reason=override if isinstance(override, str) else None)
    if previous == status:
        return {"changed": False, "status": status, "message": f"Ticket is already {status}."}
    return {"changed": True, "status": status, "message": f"Status changed to {status}."}


def _updates(conn, params):
    cursor = conn.execute("SELECT COALESCE(MAX(id), 0) FROM ticket_events").fetchone()[0]
    after = (params.get("after") or [""])[0].strip()
    changes = []
    if after:
        try:
            after_id = int(after)
        except ValueError:
            raise ApiError(400, "after must be a whole number.", "bad_request") from None
        rows = conn.execute(
            "SELECT ticket_id, status, time FROM ticket_events WHERE id IN "
            "(SELECT MAX(id) FROM ticket_events WHERE id > ? GROUP BY ticket_id) ORDER BY id",
            (after_id,)).fetchall()
        changes = [{"ticket_id": r[0], "status": r[1], "time": r[2]} for r in rows]
    return {"cursor": cursor, "changes": changes}


# -- the handler ------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "HireEmberDashboard"
    protocol_version = "HTTP/1.0"

    def log_message(self, format, *args):  # noqa: A002 - keep the console quiet
        pass

    # guards
    def _allowed_hosts(self) -> tuple[str, str]:
        port = self.server.server_address[1]
        return f"127.0.0.1:{port}", f"localhost:{port}"

    def _guard(self, method: str) -> None:
        if self.headers.get("Host", "") not in self._allowed_hosts():
            raise ApiError(403, "Forbidden host.", "forbidden")
        origin = self.headers.get("Origin")
        if method in _WRITE_METHODS and origin is not None:
            port = self.server.server_address[1]
            if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                raise ApiError(403, "Forbidden origin.", "forbidden")

    # responses
    def _send(self, status: int, body: bytes, content_type: str, headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Invalid Content-Length.", "bad_request") from None
        if length > MAX_BODY:
            raise ApiError(413, "Request is too large (max 10 MB).", "too_large")
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> dict:
        raw = self._read_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ApiError(400, "Request body must be JSON.", "bad_request") from None
        if not isinstance(data, dict):
            raise ApiError(400, "Request body must be a JSON object.", "bad_request")
        return data

    # dispatch
    def _handle(self, method: str) -> None:
        conn = None
        try:
            self._guard(method)
            parts = urlsplit(self.path)
            path, params = parts.path, parse_qs(parts.query, keep_blank_values=True)
            if method == "GET" and path in ("/", "/index.html"):
                self._send(200, _INDEX.read_bytes(), "text/html; charset=utf-8")
                return
            conn = database.get_connection(self.server.db_path)
            self._route(conn, method, path, params)
        except ApiError as exc:
            self._json(exc.status, {"error": exc.message, "code": exc.code, **exc.extra})
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                self._json(503, {"error": "Database is busy. Try again.", "code": "busy"})
            else:
                raise
        finally:
            if conn is not None:
                database.close_connection(self.server.db_path)

    def _route(self, conn, method: str, path: str, params: dict) -> None:
        if method == "GET":
            self._route_get(conn, path, params)
        else:
            self._route_write(conn, method, path)

    def _route_get(self, conn, path: str, params: dict) -> None:
        if path == "/api/tickets":
            self._json(200, _tickets_list(conn, params))
        elif m := re.fullmatch(r"/api/tickets/(\d+)", path):
            try:
                self._json(200, _ticket_detail(conn, int(m.group(1))))
            except tickets.TicketNotFoundError as exc:
                raise ApiError(404, str(exc), "not_found") from None
        elif path == "/api/blocked":
            self._json(200, _blocked(conn))
        elif path == "/api/updates":
            self._json(200, _updates(conn, params))
        elif path == "/api/export.csv":
            flt, sort, direction = _view_args(params)
            try:
                text = queries.tickets_csv(conn, flt, sort, direction)
            except ValueError as exc:
                raise ApiError(400, str(exc), "bad_filter") from None
            name = f'attachment; filename="hireember-tickets-{date.today().isoformat()}.csv"'
            self._send(200, b"\xef\xbb\xbf" + text.encode("utf-8"), "text/csv; charset=utf-8",
                       {"Content-Disposition": name})
        elif path == "/runs":
            fragment = (params.get("fragment") or [""])[0] not in ("", "0")
            self._send(200, queries.runs_html(conn, fragment).encode("utf-8"),
                       "text/html; charset=utf-8")
        elif path == "/api/runs":
            self._json(200, {"runs": [asdict(r) for r in runs.list_runs(conn)]})
        elif path == "/api/stages/status":
            last = runs.last_stage_result(conn)
            self._json(200, {"running": runs.is_running(conn),
                             "last": {"stage": last.get("stage"), "message": last.get("message")}
                             if last else None})
        elif path == "/api/answers":
            self._json(200, _answers(conn))
        elif path == "/api/resumes":
            self._json(200, _resumes(conn))
        else:
            raise ApiError(404, "Not found.", "not_found")

    def _route_write(self, conn, method: str, path: str) -> None:
        try:
            self._write(conn, method, path)
        except tickets.DuplicateTicketError as exc:
            raise ApiError(409, str(exc), "duplicate", duplicate_of=exc.duplicate_of) from None
        except tickets.OverrideReasonError as exc:
            raise ApiError(400, str(exc), "override_reason") from None
        except tickets.TicketNotFoundError as exc:
            raise ApiError(404, str(exc), "not_found") from None
        except (tickets.InvalidStatusError, tickets.TicketError, answers.QueueError,
                answers.SensitiveQuestionError) as exc:
            raise ApiError(400, str(exc), "bad_request") from None
        except answers.AnswerError as exc:
            missing = str(exc).endswith("not found.")
            raise ApiError(404 if missing else 400, str(exc),
                           "not_found" if missing else "bad_request") from None
        except resumes.ResumeError as exc:
            missing = str(exc).startswith("No resume with id")
            raise ApiError(404 if missing else 400, str(exc),
                           "not_found" if missing else "bad_request") from None

    def _write(self, conn, method: str, path: str) -> None:
        if method == "POST" and (m := re.fullmatch(r"/api/tickets/(\d+)/status", path)):
            self._json(200, _change_status(conn, int(m.group(1)), self._json_body()))
        elif method == "POST" and (m := re.fullmatch(
                r"/api/tickets/(\d+)/(note|referral-note)", path)):
            kind = "note" if m.group(2) == "note" else "referral note"
            tickets.set_note(conn, int(m.group(1)), _text(self._json_body(), "text"), kind=kind)
            self._json(200, {"ok": True})
        elif method == "POST" and (m := re.fullmatch(r"/api/queue/(\d+)/answer", path)):
            result = answers.answer_queue_item(conn, int(m.group(1)),
                                               _text(self._json_body(), "answer"))
            self._json(200, {"saved": result.saved, "message": result.message})
        elif method == "POST" and path == "/api/answers/merge":
            body = self._json_body()
            answers.merge_answers(conn, _id(body, "keep_id"), _id(body, "remove_id"),
                                  question=body.get("question"), answer=body.get("answer"))
            self._json(200, {"ok": True})
        elif method == "POST" and (m := re.fullmatch(r"/api/stages/([\w-]+)", path)):
            self._start_stage(m.group(1))
        elif method == "PUT" and (m := re.fullmatch(r"/api/answers/(\d+)", path)):
            body = self._json_body()
            answers.update_answer(conn, int(m.group(1)), _text(body, "question"),
                                  _text(body, "answer"))
            self._json(200, {"ok": True, "message": "Answer saved."})
        elif method == "DELETE" and (m := re.fullmatch(r"/api/answers/(\d+)", path)):
            answers.delete_answer(conn, int(m.group(1)))
            self._json(200, {"ok": True})
        elif method == "PUT" and (m := re.fullmatch(r"/api/resumes/(\d+)", path)):
            body = self._json_body()
            resumes.update_resume_meta(conn, int(m.group(1)), _text(body, "name"),
                                       _text(body, "tags"))
            self._json(200, {"ok": True, "message": "Resume saved."})
        elif method == "POST" and (m := re.fullmatch(r"/api/resumes/(\d+)/file", path)):
            self._replace_resume_file(conn, int(m.group(1)))
        else:
            raise ApiError(404, "Not found.", "not_found")

    def _start_stage(self, stage: str) -> None:
        if stage not in runs.STAGE_NAMES:
            raise ApiError(404, "Not found.", "not_found")
        limit = self._json_body().get("limit")
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
            raise ApiError(400, "limit must be a whole number of at least 1.", "bad_request")
        try:
            runs.start_stage_async(stage, stages=self.server.stages, limit=limit,
                                   conn=database.get_connection(self.server.db_path))
        except runs.RunInProgressError as exc:
            raise ApiError(409, str(exc), "run_in_progress") from None
        self._json(202, {"started": True, "stage": stage})

    def _replace_resume_file(self, conn, resume_id: int) -> None:
        name = Path(self.headers.get("X-Filename", "").replace("\\", "/")).name
        data = self._read_body()
        with tempfile.TemporaryDirectory(prefix="hireember-upload-") as tmp:
            target = Path(tmp) / (name or "upload")
            target.write_bytes(data)
            resumes.update_resume(conn, resume_id, target)
        self._json(200, {"ok": True, "message": "Resume file replaced."})

    def do_GET(self):  # noqa: N802
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def do_PUT(self):  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self):  # noqa: N802
        self._handle("DELETE")


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path, stages=None):
        self.db_path = db_path
        self.stages = stages
        super().__init__(address, Handler)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                  db_path: str | Path | None = None,
                  stages: runs.Stages | None = None) -> ThreadingHTTPServer:
    """Create (but do not start) the dashboard server; only 127.0.0.1 is allowed.

    ``stages`` replaces the real stage callables (used by tests).
    """
    if host != DEFAULT_HOST:
        raise HostRefusedError(host)
    server = DashboardServer((host, port), db_path, stages)
    database.init_db(db_path)
    return server


def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, open_browser: bool = False) -> None:
    """Run the dashboard until Ctrl+C."""
    server = create_server(host, port)
    url = f"http://{DEFAULT_HOST}:{server.server_address[1]}"
    print(f"HireEmber dashboard running at {url} (local only). Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
