"""Phase 2: behaviour that must not change (phase 1 tickets and existing validator)."""

import pytest

from hireember.database import close_connection, init_db

from p2_helpers import add_job, profile, tailor_json


def test_scoring_still_creates_ticket_by_threshold(tmp_path):
    from hireember.tickets import get_ticket

    db = tmp_path / "hireember.db"
    conn = init_db(db)
    try:
        lo = get_ticket(conn, add_job(conn, "https://j.example/lo", score=6))
        hi = get_ticket(conn, add_job(conn, "https://j.example/hi", score=7))
        assert lo["status"] == "skipped" and lo["status_reason"] == "score 6 below threshold 7"
        assert hi["status"] == "pending"
    finally:
        close_connection(db)


def test_existing_json_validation_still_rejects_missing_fields():
    from hireember.scoring.validator import validate_json_fields

    res = validate_json_fields({"title": "x"}, profile(), mode="lenient")
    assert res["passed"] is False
    assert "Missing required field: summary" in res["errors"]


def test_valid_tailor_json_still_passes():
    from hireember.scoring.validator import validate_json_fields

    assert validate_json_fields(tailor_json(), profile(), mode="lenient")["passed"] is True
