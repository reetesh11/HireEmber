"""The real stage callables a run drives (discover, enrich, score, tailor, apply)."""

from __future__ import annotations

import sqlite3

from hireember.runs import Stages


def default_stages(min_score: int | None = None, validation_mode: str = "normal") -> Stages:
    """Stages backed by the existing discovery, enrichment, scoring, tailoring and apply code."""

    def discover(conn: sqlite3.Connection, run_id: int | None) -> dict:
        from hireember.discovery.companies import discover_companies

        return discover_companies(conn, run_id=run_id)

    def enrich(conn: sqlite3.Connection, run_id: int | None) -> dict:
        from hireember.enrichment.detail import run_enrichment

        return run_enrichment() or {}

    def score(conn: sqlite3.Connection, run_id: int | None) -> dict:
        from hireember.scoring.scorer import run_scoring
        from hireember.tickets import _now

        started = _now()
        result = run_scoring() or {}
        # Location skips open a skipped ticket, so counting skipped tickets covers them too.
        skipped = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE status = 'skipped' AND created_at >= ?",
            (started,)).fetchone()[0]
        return {"scored": result.get("scored", 0),
                "skipped": max(skipped, result.get("location_skipped", 0))}

    def tailor(conn: sqlite3.Connection, run_id: int | None) -> dict:
        from hireember.scoring.tailor import run_tailoring
        from hireember.tickets import get_threshold

        result = run_tailoring(
            min_score=min_score if min_score is not None else get_threshold(conn),
            validation_mode=validation_mode) or {}
        return {"created": result.get("approved", 0),
                "blocked": result.get("failed", 0) + result.get("errors", 0)}

    def apply(conn: sqlite3.Connection, run_id: int | None, limit: int) -> dict:
        from hireember.apply import launcher

        return {"submitted": launcher.main(limit=limit, headless=True) or 0}

    return Stages(discover=discover, enrich=enrich, score=score, tailor=tailor, apply=apply)
