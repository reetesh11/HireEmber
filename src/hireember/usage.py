"""Model and token usage per ticket stage (scoring, tailoring, applying)."""

from __future__ import annotations

import contextvars
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass

from hireember import tickets

STAGES = ("scoring", "tailoring", "applying")


@dataclass
class Collected:
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


_current: contextvars.ContextVar[Collected | None] = contextvars.ContextVar(
    "hireember_usage_collector", default=None)


def _tokens(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


@contextmanager
def collect():
    """Collect the model calls made inside the block (isolated per thread and per nested block)."""
    collected = Collected()
    token = _current.set(collected)
    try:
        yield collected
    finally:
        _current.reset(token)


def note_call(model: str, input_tokens, output_tokens) -> None:
    """Add one model call to the active collector; does nothing outside ``collect()``."""
    collected = _current.get()
    if collected is None:
        return
    collected.model = model or collected.model
    collected.input_tokens += _tokens(input_tokens)
    collected.output_tokens += _tokens(output_tokens)
    collected.calls += 1


def record(conn: sqlite3.Connection, ticket_id: int, stage: str, model: str,
           input_tokens: int = 0, output_tokens: int = 0) -> None:
    """Add tokens to the ticket's row for the stage; the model is the latest one seen."""
    if stage not in STAGES:
        raise ValueError(f"Unknown stage {stage!r}. Valid stages: {', '.join(STAGES)}.")
    inp, out = _tokens(input_tokens), _tokens(output_tokens)
    conn.execute(
        "INSERT INTO stage_usage (ticket_id, stage, model, input_tokens, output_tokens, "
        "total_tokens, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(ticket_id, stage) DO UPDATE SET model = excluded.model, "
        "input_tokens = input_tokens + excluded.input_tokens, "
        "output_tokens = output_tokens + excluded.output_tokens, "
        "total_tokens = total_tokens + excluded.total_tokens, updated_at = excluded.updated_at",
        (ticket_id, stage, model or "unknown", inp, out, inp + out, tickets._now()))
    conn.commit()


def record_collected(conn: sqlite3.Connection, ticket_id: int, stage: str,
                     collected: Collected) -> None:
    if collected.calls > 0:
        record(conn, ticket_id, stage, collected.model, collected.input_tokens,
               collected.output_tokens)


def get_usage(conn: sqlite3.Connection, ticket_id: int) -> dict:
    result: dict = {s: None for s in STAGES}
    rows = conn.execute("SELECT stage, model, input_tokens, output_tokens, total_tokens "
                        "FROM stage_usage WHERE ticket_id = ?", (ticket_id,)).fetchall()
    for r in rows:
        if r[0] in result:
            result[r[0]] = {"model": r[1] or "unknown", "input_tokens": r[2] or 0,
                            "output_tokens": r[3] or 0, "total_tokens": r[4] or 0}
    return result
