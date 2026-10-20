"""Shared helpers for the phase-0e acceptance tests (public surfaces only)."""

import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from rich.console import Console

ENV_VARS = ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY")
SECRET = "sk-SECRET-VALUE-12345"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def isolate_models(monkeypatch, tmp_path) -> Path:
    """Clear every legacy LLM variable and point the models file at tmp; return its path."""
    from hireember import config

    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "models.toml"
    monkeypatch.setattr(config, "MODELS_PATH", path, raising=False)
    return path


def write_models(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def wide_console() -> Console:
    return Console(file=io.StringIO(), width=300)


def output(c: Console) -> str:
    return c.file.getvalue()


class FakeClient:
    def __init__(self, reply="ok", error=None):
        self.reply = reply
        self.error = error
        self.calls = 0

    def chat(self, messages, max_tokens=None, temperature=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply

    def ask(self, prompt, **kwargs):
        return self.chat([{"role": "user", "content": prompt}])


class ProbeServer:
    """A local HTTP server answering every GET with ``status``; records request paths."""

    def __init__(self, status=200):
        self.status = status
        self.paths: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                outer.paths.append(self.path)
                self.send_response(outer.status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            do_POST = do_GET

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def free_port_url() -> str:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/v1"
