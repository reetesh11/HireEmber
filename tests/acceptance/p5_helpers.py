"""Shared helpers for the phase-5 scheduler / company list acceptance tests (public surfaces only)."""

import threading
from datetime import datetime, timezone

from p4_helpers import make_ticket  # noqa: F401  (re-exported)


def utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


class Recorder:
    """Builds a runs.Stages whose callables record calls and return canned results."""

    def __init__(self, found=5, new=3, scored=4, skipped=1, created=0, blocked=0, submitted=0,
                 hooks=None):
        self.calls = []
        self.apply_limits = []
        self.results = {
            "discover": {"found": found, "new": new},
            "enrich": {},
            "score": {"scored": scored, "skipped": skipped},
            "tailor": {"created": created, "blocked": blocked},
            "apply": {"submitted": submitted},
        }
        self.hooks = hooks or {}

    def _make(self, name):
        def stage(conn, run_id, *extra):
            self.calls.append(name)
            if name == "apply":
                self.apply_limits.append(extra[0])
            hook = self.hooks.get(name)
            if hook:
                hook(conn, run_id)
            return self.results[name]
        return stage

    def stages(self):
        from hireember.runs import Stages

        return Stages(**{n: self._make(n) for n in ("discover", "enrich", "score", "tailor", "apply")})


def blocking_stages(entered: threading.Event, release: threading.Event):
    """Stages whose discover blocks until ``release`` is set (to hold the run lock)."""
    rec = Recorder(hooks={"discover": lambda conn, run_id: (entered.set(), release.wait(15))})
    return rec


def run_rows(conn):
    return conn.execute("SELECT * FROM runs ORDER BY id").fetchall()
