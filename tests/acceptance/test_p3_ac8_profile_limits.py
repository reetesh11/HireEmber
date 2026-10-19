"""Phase 3 AC-8: the default Chrome profile is refused; per-company, daily and one-day limits hold in a batch."""

from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from p3_helpers import SESSION_LINK, add_ticket, agent_for, forbidden_agent, make_env

REFUSAL = "Refusing to use the default Chrome profile. HireEmber uses its own browser profile."

@pytest.fixture
def env(isolated_db, tmp_path, monkeypatch):
    return make_env(tmp_path, monkeypatch)



def _default_profile_dir():
    import hireember.config as config

    return config.get_chrome_user_data()


def test_assert_dedicated_profile_refuses_the_default_profile_and_children():
    from hireember.apply.chrome import DefaultProfileError, assert_dedicated_profile

    default = _default_profile_dir()
    for path in (default, default / "Default", default.parent):
        with pytest.raises(DefaultProfileError) as exc:
            assert_dedicated_profile(path)
        assert str(exc.value) == REFUSAL
    assert issubclass(DefaultProfileError, ValueError)


def test_dedicated_worker_profiles_are_accepted(tmp_path, monkeypatch):
    import hireember.config as config
    from hireember.apply.chrome import assert_dedicated_profile, check_worker_profiles

    monkeypatch.setattr(config, "CHROME_WORKER_DIR", tmp_path / "chrome-workers")

    check_worker_profiles(3)
    assert_dedicated_profile(tmp_path / "chrome-workers" / "worker-0")


def test_check_worker_profiles_refuses_when_workers_point_at_the_default(monkeypatch):
    import hireember.config as config
    from hireember.apply.chrome import DefaultProfileError, check_worker_profiles

    monkeypatch.setattr(config, "CHROME_WORKER_DIR", _default_profile_dir().parent)

    with pytest.raises(DefaultProfileError):
        check_worker_profiles(1)


def test_cli_apply_refuses_default_profile_without_launching_chrome(isolated_db, monkeypatch):
    import hireember.apply.chrome as chrome_mod
    import hireember.config as config
    from hireember.apply import launcher
    from hireember.cli import app

    calls = []
    monkeypatch.setattr(config, "CHROME_WORKER_DIR", _default_profile_dir().parent)
    monkeypatch.setattr(launcher, "launch_chrome", lambda *a, **k: calls.append("launch_chrome"))
    monkeypatch.setattr(chrome_mod, "launch_chrome", lambda *a, **k: calls.append("chrome.launch_chrome"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: calls.append("Popen"))
    monkeypatch.setattr(launcher, "main", lambda *a, **k: calls.append("main"))

    result = CliRunner().invoke(app, ["apply"])

    assert result.exit_code == 1, result.output
    assert REFUSAL in " ".join(result.output.split())
    assert calls == []


def test_fourth_open_ticket_for_a_company_is_held(env):
    from hireember.apply.limits import check_limits
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket, set_status

    conn, tmp = env
    for i in range(3):
        tid = add_ticket(conn, tmp, f"l{i}")
        set_status(conn, tid, "started")
    fourth = add_ticket(conn, tmp, "l3")

    result = check_limits(conn, fourth)
    assert result.ok is False and result.reason.startswith("limit: company")

    outcome = apply_ticket(conn, fourth, forbidden_agent, session_link=SESSION_LINK)

    assert outcome.result == "held"
    ticket = get_ticket(conn, fourth)
    assert ticket["status"] == "pending"
    assert ticket["status_reason"].startswith("limit: company")


def test_second_ticket_for_a_company_waits_one_day_but_other_companies_go(env, fixture_form_server):
    from hireember.apply.limits import check_limits, eligible_ticket_ids
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket
    from hireember.apply import launcher

    conn, tmp = env
    first = add_ticket(conn, tmp, "w1", score=9)
    waiting = add_ticket(conn, tmp, "w2", score=8)
    other = add_ticket(conn, tmp, "w3", company="Other Co", score=7)
    agent, _ = agent_for(fixture_form_server, "upload_form.html")
    assert apply_ticket(conn, first, agent, session_link=SESSION_LINK).result == "applied"
    now = datetime.now(timezone.utc)

    outcome = apply_ticket(conn, waiting, forbidden_agent, session_link=SESSION_LINK)

    assert outcome.result == "held"
    ticket = get_ticket(conn, waiting)
    assert ticket["status"] == "pending"
    assert ticket["status_reason"].startswith("limit: company wait until")
    not_before = datetime.fromisoformat(ticket["not_before"])
    assert timedelta(hours=23) < not_before - now <= timedelta(hours=24, minutes=1)
    assert waiting not in eligible_ticket_ids(conn, now)
    assert other in eligible_ticket_ids(conn, now)
    assert launcher.acquire_job(min_score=1)["url"] == "https://jobs.example/w3"
    assert launcher.acquire_job(min_score=1) is None, "the held ticket's job must not be picked"

    later = now + timedelta(hours=25)
    assert check_limits(conn, waiting, later).ok is True
    assert waiting in eligible_ticket_ids(conn, later)


def test_daily_limit_holds_the_next_ticket_until_tomorrow(env, fixture_form_server):
    from hireember.apply.runner import apply_ticket
    from hireember.tickets import get_ticket, set_setting

    conn, tmp = env
    set_setting(conn, "max_per_day", "2")
    for i in range(2):
        tid = add_ticket(conn, tmp, f"day{i}", company=f"Day Co {i}")
        agent, _ = agent_for(fixture_form_server, "upload_form.html")
        assert apply_ticket(conn, tid, agent, session_link=SESSION_LINK).result == "applied"
    third = add_ticket(conn, tmp, "day2", company="Day Co 2")

    outcome = apply_ticket(conn, third, forbidden_agent, session_link=SESSION_LINK)

    assert outcome.result == "held"
    ticket = get_ticket(conn, third)
    assert ticket["status"] == "pending" and ticket["status_reason"] == "limit: daily"
    not_before = datetime.fromisoformat(ticket["not_before"])
    assert datetime.now(timezone.utc) < not_before <= datetime.now(timezone.utc) + timedelta(days=1, minutes=1)
    assert not_before.hour == 0 and not_before.minute == 0


def test_defaults_are_three_open_twenty_five_a_day_one_day_wait():
    from hireember.apply import limits

    assert limits.DEFAULT_MAX_OPEN_PER_COMPANY == 3
    assert limits.DEFAULT_MAX_PER_DAY == 25
    assert limits.DEFAULT_COMPANY_WAIT_HOURS == 24
