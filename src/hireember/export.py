"""CSV export of tickets and runs."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from dataclasses import astuple
from pathlib import Path

from hireember import runs
from hireember.web import queries

RUNS_HEADER = ("id", "kind", "trigger", "status", "started_at", "ended_at", "found", "scored",
               "skipped", "tickets_created", "tickets_blocked")


class ExportError(Exception):
    """The export folder cannot be written to."""


def _runs_csv(conn: sqlite3.Connection) -> tuple[str, int]:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(RUNS_HEADER)
    rows = list(reversed(runs.list_runs(conn, limit=-1)))
    for r in rows:
        writer.writerow([queries._guard(v) if isinstance(v, str) else ("" if v is None else v)
                         for v in astuple(r)])
    return out.getvalue(), len(rows)


def export_csv(conn: sqlite3.Connection, out_dir: str | Path) -> list[tuple[Path, int]]:
    """Write tickets.csv and runs.csv into ``out_dir``; return (path, row count) for each."""
    folder = Path(out_dir)
    if not folder.exists():
        raise ExportError(f"Folder not found: {folder}. Create it or choose another with --out.")
    if not folder.is_dir():
        raise ExportError(f"Not a folder: {folder}. Choose a folder with --out.")
    if not os.access(folder, os.W_OK | os.X_OK):
        raise ExportError(f"Cannot write to {folder}. Choose another folder with --out.")
    tickets_text = queries.tickets_csv(conn)
    tickets_rows = max(0, len(list(csv.reader(io.StringIO(tickets_text, newline="")))) - 1)
    runs_text, runs_rows = _runs_csv(conn)
    results = []
    for name, text, count in (("tickets.csv", tickets_text, tickets_rows),
                              ("runs.csv", runs_text, runs_rows)):
        path = folder / name
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        except OSError as e:
            raise ExportError(f"Cannot write {path}: {e.strerror or e}.") from None
        results.append((path, count))
    return results
