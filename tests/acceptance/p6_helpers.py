"""Shared helpers for the phase-6 release hardening acceptance tests (public surfaces only)."""

import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

from p4_helpers import Client, make_ticket, start_server, stop_server  # noqa: F401  (re-exported)
from p5_helpers import Recorder, utc  # noqa: F401  (re-exported)

REPO_ROOT = Path(__file__).resolve().parents[2]


def use_log_dir(monkeypatch, tmp_path) -> Path:
    """Point the log folder at a temporary directory (read at call time) and return it."""
    import hireember.config as config

    root = tmp_path / "logs"
    monkeypatch.setattr(config, "LOG_DIR", root)
    return root


class FakeHttp:
    """Stands in for ``LLMClient._client``: answers every POST from ``respond(url, json)``."""

    def __init__(self, respond):
        self.respond = respond
        self.calls = 0

    def post(self, url, json=None, headers=None, params=None, **kwargs):
        self.calls += 1
        status, body = self.respond(url, json)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    def close(self):
        pass


def openai_body(text, prompt=None, completion=None):
    body = {"choices": [{"message": {"content": text}}]}
    if prompt is not None:
        body["usage"] = {"prompt_tokens": prompt, "completion_tokens": completion or 0}
    return body


def make_llm(model, respond):
    """A real LLMClient whose HTTP layer is replaced by ``respond``; returns (client, fake)."""
    from hireember.llm import LLMClient

    client = LLMClient("http://localhost:1/v1", model, "")
    fake = FakeHttp(respond)
    client._client = fake
    return client, fake


class _Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def table_rows(html: str) -> list[list[str]]:
    parser = _Tables()
    parser.feed(html)
    return parser.rows


def usage_row(html: str, stage: str) -> list[str]:
    for row in table_rows(html):
        if row and row[0] == stage:
            return row
    raise AssertionError(f"no {stage!r} row in the page tables: {table_rows(html)!r}")


def heading_section(text: str, heading_re: str) -> str:
    """Text from the first markdown heading matching ``heading_re`` to the next heading of the
    same or a higher level (or the end)."""
    lines = text.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        m = re.match(r"^(#+)\s+(.*)$", line)
        if m and re.search(heading_re, m.group(2)):
            start, level = i, len(m.group(1))
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        m = re.match(r"^(#+)\s", lines[j])
        if m and len(m.group(1)) <= level:
            end = j
            break
    return "\n".join(lines[start:end])
