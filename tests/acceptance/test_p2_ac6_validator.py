"""Phase 2 AC-6: the validator rejects facts outside the profile; retries end in a blocked ticket."""

import pytest
from typer.testing import CliRunner

from hireember.database import close_connection, init_db

from p2_helpers import (bad_employer_tailor, bad_skill_tailor, install_fake_llm, make_resume, profile,
                        store_job, tailor_json, widen_cli_console)


def test_valid_text_has_no_reasons():
    from hireember.scoring.validator import validate_against_profile

    assert validate_against_profile(tailor_json(), profile()) == []


def test_employer_outside_profile_rejected():
    from hireember.scoring.validator import validate_against_profile

    assert validate_against_profile(bad_employer_tailor(), profile()) == [
        'employer "Acme Corp" not in resume facts']


def test_skill_outside_boundary_rejected():
    from hireember.scoring.validator import validate_against_profile

    assert validate_against_profile(bad_skill_tailor(), profile()) == [
        'skill "Kubernetes" not in skills boundary']


def test_project_outside_profile_rejected():
    from hireember.scoring.validator import validate_against_profile

    data = tailor_json(projects=[{"header": "Project Z", "subtitle": "Python", "bullets": ["Wrote a parser."]}])
    assert validate_against_profile(data, profile()) == ['project "Project Z" not in resume facts']


def test_metric_outside_profile_rejected():
    from hireember.scoring.validator import validate_against_profile

    data = tailor_json()
    data["experience"][0]["bullets"] = ["Cut latency by 95% on the API."]
    reasons = validate_against_profile(data, profile())
    assert len(reasons) == 1
    assert reasons[0].startswith('metric "') and "95%" in reasons[0]
    assert reasons[0].endswith('not in resume facts')


def test_validate_json_fields_includes_the_reasons():
    from hireember.scoring.validator import validate_json_fields

    ok = validate_json_fields(tailor_json(), profile(), mode="lenient")
    assert ok["passed"] is True and ok["errors"] == []
    bad = validate_json_fields(bad_employer_tailor(), profile(), mode="lenient")
    assert bad["passed"] is False
    assert 'employer "Acme Corp" not in resume facts' in bad["errors"]
    bad = validate_json_fields(bad_skill_tailor(), profile(), mode="lenient")
    assert 'skill "Kubernetes" not in skills boundary' in bad["errors"]


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    from hireember import config
    config.ensure_dirs()
    make_resume(conn, tmp_path, "Backend", "backend", "BASE RESUME TEXT")
    yield conn
    close_connection(db)


def _pending_ticket(conn, url, monkeypatch, tailor):
    from hireember.gating import score_job_for_ticket

    fake = install_fake_llm(monkeypatch, tailor=tailor)
    res = score_job_for_ticket(conn, store_job(conn, url), profile=profile())
    assert res.status == "pending"
    return fake, res.ticket_id


@pytest.mark.parametrize("which,reason", [
    (bad_employer_tailor, 'employer "Acme Corp" not in resume facts'),
    (bad_skill_tailor, 'skill "Kubernetes" not in skills boundary'),
])
def test_retry_limit_blocks_ticket_with_reason(env, monkeypatch, which, reason):
    from hireember.gating import tailor_ticket
    from hireember.tickets import get_history, get_ticket

    fake, tid = _pending_ticket(env, "https://j.example/v", monkeypatch, which())
    res = tailor_ticket(env, tid, profile=profile(), validation_mode="lenient", max_retries=1)
    assert len(fake.calls["tailor"]) == 2  # first attempt plus one retry
    assert res.status == "blocked for human"
    assert res.reason == f"validation failed: {reason}"
    t = get_ticket(env, tid)
    assert t["status"] == "blocked for human" and t["status_reason"] == f"validation failed: {reason}"
    assert t["tailored_resume_path"] is None and t["cover_letter_path"] is None
    assert get_history(env, tid)[-1]["reason"] == f"validation failed: {reason}"


def test_process_job_blocks_after_default_retries_and_status_shows_reason(env, monkeypatch, isolated_db):
    from hireember.cli import app
    from hireember.gating import process_job
    from hireember.tickets import get_ticket

    widen_cli_console(monkeypatch)
    fake = install_fake_llm(monkeypatch, tailor=bad_employer_tailor())
    res = process_job(env, store_job(env, "https://j.example/p"), profile=profile(),
                      validation_mode="lenient")
    reason = 'validation failed: employer "Acme Corp" not in resume facts'
    assert res.status == "blocked for human" and res.reason == reason
    assert len(fake.calls["tailor"]) >= 2
    assert get_ticket(env, res.ticket_id)["status_reason"] == reason

    out = CliRunner().invoke(app, ["status"])
    assert out.exit_code == 0, out.output
    assert "Tickets needing attention" in out.output
    assert reason in out.output
    assert "blocked for human" in out.output
