"""Phase 2 AC-7: roles below the threshold are skipped; every scored role has a score and reason."""

import pytest

from hireember.database import close_connection, init_db

from p2_helpers import install_fake_llm, make_resume, profile, store_job


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    from hireember import config
    config.ensure_dirs()
    yield c
    close_connection(db)


@pytest.fixture
def resume(conn, tmp_path):
    return make_resume(conn, tmp_path, "Backend", "backend", "BASE RESUME TEXT")


def test_below_threshold_is_skipped_and_not_tailored(conn, resume, monkeypatch):
    from hireember.gating import process_job
    from hireember.tickets import get_history, get_ticket

    fake = install_fake_llm(monkeypatch, score=6, reasoning="Weak fit.")
    res = process_job(conn, store_job(conn, "https://j.example/low"), profile=profile())
    assert res.status == "skipped" and res.reason == "score 6 below threshold 7"
    assert res.score == 6
    t = get_ticket(conn, res.ticket_id)
    assert t["status"] == "skipped" and t["status_reason"] == "score 6 below threshold 7"
    assert t["score"] == 6 and t["score_reason"] == "Weak fit."
    assert t["resume_id"] == resume
    assert t["tailored_resume_path"] is None and t["cover_letter_path"] is None
    assert fake.calls["tailor"] == [] and fake.calls["cover_letter"] == []
    assert get_history(conn, res.ticket_id)[-1]["status"] == "skipped"
    job = conn.execute("SELECT apply_status, applied_at, apply_attempts FROM jobs").fetchone()
    assert job[0] is None and job[1] is None and not job[2]


def test_exactly_threshold_is_not_skipped(conn, resume, monkeypatch):
    from hireember.gating import score_job_for_ticket

    install_fake_llm(monkeypatch, score=7)
    res = score_job_for_ticket(conn, store_job(conn, "https://j.example/eq"), profile=profile())
    assert res.status == "pending" and res.score == 7


def test_custom_threshold_setting_is_used(conn, resume, monkeypatch):
    from hireember.gating import score_job_for_ticket
    from hireember.tickets import set_setting

    set_setting(conn, "score_threshold", "9")
    install_fake_llm(monkeypatch, score=8)
    res = score_job_for_ticket(conn, store_job(conn, "https://j.example/nine"), profile=profile())
    assert res.status == "skipped" and res.reason == "score 8 below threshold 9"


def test_every_scored_role_has_score_and_reason(conn, resume, monkeypatch):
    from hireember.gating import score_job_for_ticket
    from hireember.tickets import get_ticket

    install_fake_llm(monkeypatch, score=9, reasoning="")
    res = score_job_for_ticket(conn, store_job(conn, "https://j.example/noreason"), profile=profile())
    t = get_ticket(conn, res.ticket_id)
    assert 1 <= t["score"] <= 10
    assert t["score_reason"] and t["score_reason"].strip()


def test_prompt_carries_profile_target_roles_location_level(conn, resume, monkeypatch):
    from hireember.gating import score_job_for_ticket

    fake = install_fake_llm(monkeypatch, score=8)
    p = profile()
    p["experience"]["target_role"] = "zanzibar engineer"
    score_job_for_ticket(conn, store_job(conn, "https://j.example/prompt"), profile=p)
    assert "zanzibar engineer" in fake.texts("scorer")


def test_no_base_resume_blocks_without_llm(conn, monkeypatch):
    from hireember.gating import process_job
    from hireember.tickets import get_ticket

    fake = install_fake_llm(monkeypatch)
    res = process_job(conn, store_job(conn, "https://j.example/nores"), profile=profile())
    assert res.status == "blocked for human" and res.reason == "no base resume"
    t = get_ticket(conn, res.ticket_id)
    assert t["status"] == "blocked for human" and t["status_reason"] == "no base resume"
    assert t["resume_id"] is None
    assert not any(fake.calls.values())


def test_llm_error_blocks_and_stores_no_score(conn, resume, monkeypatch):
    from hireember.gating import process_job
    from hireember.tickets import get_ticket

    fake = install_fake_llm(monkeypatch, score_error="boom")
    res = process_job(conn, store_job(conn, "https://j.example/err"), profile=profile())
    assert res.status == "blocked for human" and res.reason.startswith("LLM error")
    assert "boom" in res.reason
    t = get_ticket(conn, res.ticket_id)
    assert t["status"] == "blocked for human" and t["score"] is None
    assert conn.execute("SELECT fit_score FROM jobs").fetchone()[0] is None
    assert fake.calls["tailor"] == []


def test_tailor_ticket_leaves_skipped_ticket_unchanged(conn, resume, monkeypatch):
    from hireember.gating import score_job_for_ticket, tailor_ticket
    from hireember.tickets import get_ticket

    fake = install_fake_llm(monkeypatch, score=3)
    res = score_job_for_ticket(conn, store_job(conn, "https://j.example/skip"), profile=profile())
    before = get_ticket(conn, res.ticket_id)
    out = tailor_ticket(conn, res.ticket_id, profile=profile())
    assert out.status == "skipped"
    assert get_ticket(conn, res.ticket_id) == before
    assert fake.calls["tailor"] == []


def test_profile_none_loads_saved_profile(conn, resume, monkeypatch):
    import json

    from hireember import config
    from hireember.gating import score_job_for_ticket

    install_fake_llm(monkeypatch, score=8)
    config.APP_DIR.mkdir(parents=True, exist_ok=True)
    config.PROFILE_PATH.write_text(json.dumps(profile()), encoding="utf-8")
    try:
        res = score_job_for_ticket(conn, store_job(conn, "https://j.example/default"))
    finally:
        config.PROFILE_PATH.unlink()
    assert res.status == "pending"
