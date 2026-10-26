"""AC-6, AC-7, AC-9, AC-13, AC-16: interactive fixes, declining, and continuing in the same process."""

import subprocess

import pytest
from p0f_helpers import (
    LOCAL,
    Q_BROWSER,
    Q_FAST,
    Q_KEY,
    Q_LOOKS_RIGHT,
    Q_MODEL,
    Q_PATH,
    Q_PROFILE,
    Q_PROVIDER,
    Q_QUALITY,
    Q_RESUME,
    Q_SAME,
    Q_SEARCH,
    SECRET,
    Ask,
    NeverAsk,
    World,
    flat,
    out_of,
    wide_console,
)
from typer.testing import CliRunner

import hireember.cli as cli


@pytest.fixture
def w(monkeypatch, tmp_path, isolated_db):
    monkeypatch.setenv("COLUMNS", "300")
    return World(monkeypatch, tmp_path, isolated_db)


@pytest.fixture
def calls(monkeypatch):
    rec = []

    def fake_pipeline(*args, **kwargs):
        rec.append((args, kwargs))
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr("hireember.pipeline.run_pipeline", fake_pipeline)

    def fake_run_stage(stage, **kwargs):
        # A single discover, score or tailor goes through runs.run_stage (phase 5).
        rec.append(((), {"stages": [stage]}))
        from hireember.runs import StageResult
        return StageResult(stage, f"{stage}: done.", {})

    monkeypatch.setattr("hireember.runs.run_stage", fake_run_stage)
    return rec


def stages_of(call):
    args, kwargs = call
    return list(kwargs.get("stages", args[0] if args else []))


def terminal(monkeypatch, ask):
    from hireember import preflight

    monkeypatch.setattr(preflight, "is_interactive", lambda: True)
    monkeypatch.setattr(preflight, "ask_user", ask)
    return preflight


# -- AC-6: model tier fix, through the CLI ------------------------------------------------------

def test_ac6_run_tailor_prompts_saves_models_toml_and_runs_in_the_same_process(w, calls, monkeypatch, tmp_path):
    w.tier("fast")
    w.resume()
    w.profile()
    ask = Ask({Q_QUALITY: ["y"], Q_SAME: ["n"], Q_PROVIDER: ["openai"], Q_MODEL: ["gpt-x"], Q_KEY: [SECRET]})
    terminal(monkeypatch, ask)
    res = CliRunner().invoke(cli.app, ["run", "tailor"])
    assert res.exit_code == 0, res.output
    text = flat(res.output)
    assert "Quality model" in text and "Quality model: set." in text and "All set. Starting run." in text
    assert ask.log == [Q_QUALITY, Q_SAME, Q_PROVIDER, Q_MODEL, Q_KEY]
    key_kwargs = ask.kwargs[ask.log.index(Q_KEY)]
    assert key_kwargs.get("password") is True
    assert SECRET not in res.output
    quality = w.models.load_models_file(w.models_path)["quality"]
    assert quality == w.models.load_models_file(
        _write_expected(tmp_path, "quality", provider="openai", model="gpt-x", base_url=None, api_key=SECRET)
    )["quality"]
    assert len(calls) == 1 and stages_of(calls[0]) == ["tailor"]


def _write_expected(tmp_path, tier, **fields):
    from hireember import models

    path = tmp_path / "expected_models.toml"
    models.save_tier(tier, path=path, **fields)
    return path


def test_ac6_custom_local_endpoint_asks_base_url_and_no_key(w, monkeypatch, calls, tmp_path):
    w.tier("fast")
    w.resume()
    w.profile()
    ask = Ask({Q_QUALITY: ["y"], Q_SAME: ["n"], Q_PROVIDER: ["custom"], Q_MODEL: ["llama3"], "Base URL": [LOCAL]})
    terminal(monkeypatch, ask)
    res = CliRunner().invoke(cli.app, ["run", "tailor"])
    assert res.exit_code == 0, res.output
    assert ask.log == [Q_QUALITY, Q_SAME, Q_PROVIDER, Q_MODEL, "Base URL"]
    expected = w.models.load_models_file(
        _write_expected(tmp_path, "quality", provider="custom", model="llama3", base_url=LOCAL, api_key=None))
    assert w.models.load_models_file(w.models_path)["quality"] == expected["quality"]


def test_ac6_same_as_fast_copies_the_values_and_asks_nothing_more(w, calls, monkeypatch, tmp_path):
    w.tier("fast", provider="openai", model="gpt-fast", base_url=None, api_key=SECRET)
    w.resume()
    w.profile()
    ask = Ask({Q_QUALITY: ["y"], Q_SAME: ["y"]})
    terminal(monkeypatch, ask)
    res = CliRunner().invoke(cli.app, ["run", "tailor"])
    assert res.exit_code == 0, res.output
    assert ask.log == [Q_QUALITY, Q_SAME]
    data = w.models.load_models_file(w.models_path)
    assert data["quality"]["provider"] == "openai" and data["quality"]["model"] == "gpt-fast"
    assert data["quality"]["api_key"] == SECRET
    assert SECRET not in res.output
    assert len(calls) == 1


def test_same_as_fast_copies_a_key_that_came_from_the_environment(w, monkeypatch):
    w.tier("fast", provider="openai", model="gpt-fast", base_url=None)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    w.resume()
    w.profile()
    ask = Ask({Q_QUALITY: ["y"], Q_SAME: ["y"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["tailor"], console=c)
    assert outcome.proceed is True
    assert w.models.load_models_file(w.models_path)["quality"]["api_key"] == SECRET
    assert SECRET not in out_of(c)


def test_same_as_fast_is_not_offered_when_the_fast_tier_is_not_configured(w, monkeypatch):
    w.resume()
    w.profile()
    ask = Ask({Q_QUALITY: ["y"], Q_PROVIDER: ["custom"], Q_MODEL: ["m"], "Base URL": [LOCAL]})
    preflight = terminal(monkeypatch, ask)
    outcome = preflight.run_preflight("run", ["tailor"], console=wide_console())
    assert outcome.proceed is True
    assert Q_SAME not in ask.log


def test_fast_tier_fix_never_offers_same_as_fast(w, monkeypatch):
    w.resume()
    w.profile()
    ask = Ask({Q_FAST: ["y"], Q_PROVIDER: ["custom"], Q_MODEL: ["m"], "Base URL": [LOCAL]})
    preflight = terminal(monkeypatch, ask)
    outcome = preflight.run_preflight("run", ["score"], console=wide_console())
    assert outcome.proceed is True and Q_SAME not in ask.log
    assert "fast" in w.models.load_models_file(w.models_path)


# -- AC-7 / AC-16: several items, in order, once each --------------------------------------------

def test_ac7_one_message_lists_all_three_then_prompts_in_listed_order(w, monkeypatch):
    w.tier("fast")
    w.profile()
    w.browser_installed = False
    ask = Ask({Q_QUALITY: ["n"], Q_RESUME: ["n"], Q_BROWSER: ["n"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["enrich", "tailor"], console=c)
    text = out_of(c)
    assert text.count("Before this run can start") == 1
    assert "3 things need setting up" in text
    assert text.index("Quality model") < text.index("Base resume") < text.index("Playwright browser")
    assert ask.log == [Q_QUALITY, Q_RESUME, Q_BROWSER]
    assert outcome.proceed is False


def test_ac16_resume_fix_registers_and_continues_without_asking_again(w, monkeypatch, tmp_path):
    from hireember import resumes

    w.tier("fast")
    w.profile()
    src = tmp_path / "my_resume.txt"
    src.write_text("Jane Doe\nSenior engineer. Built distributed systems for ten years.\n", encoding="utf-8")
    ask = Ask({Q_RESUME: ["y"], Q_PATH: [str(src)], Q_LOOKS_RIGHT: ["y"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["score"], console=c)
    assert outcome.proceed is True and outcome.stages == ["score"] and outcome.missing == []
    assert ask.log.count(Q_RESUME) == 1
    assert len(resumes.list_resumes(w.conn)) == 1
    assert w.config.RESUME_PATH.exists()
    text = out_of(c)
    assert "Base resume: set." in text and "All set. Starting run." in text


def test_ac16_already_satisfied_items_are_not_asked_about(w, monkeypatch):
    w.tier("fast")
    w.tier("quality")
    w.resume()
    w.profile()
    ask = Ask({Q_BROWSER: ["n"]})
    w.browser_installed = False
    preflight = terminal(monkeypatch, ask)
    preflight.run_preflight("run", ["score", "tailor", "enrich"], console=wide_console())
    assert ask.log == [Q_BROWSER]


def test_browser_fix_runs_playwright_install_chromium_and_continues(w, monkeypatch):
    w.everything()
    w.browser_installed = False
    ran = []

    def fake_run(cmd, *a, **k):
        ran.append(list(cmd) if not isinstance(cmd, str) else cmd.split())
        w.browser_installed = True
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    ask = Ask({Q_BROWSER: ["y"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["enrich"], console=c)
    assert outcome.proceed is True and outcome.stages == ["enrich"]
    assert len(ran) == 1 and "playwright" in ran[0] and ran[0][-2:] == ["install", "chromium"]
    assert "Playwright browser: set." in out_of(c)


def test_failed_browser_install_keeps_the_item_missing_and_shows_the_manual_command(w, monkeypatch):
    w.everything()
    w.browser_installed = False
    monkeypatch.setattr(subprocess, "run", lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, 1))
    ask = Ask({Q_BROWSER: ["y", "n"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["enrich"], console=c)
    assert outcome.proceed is False
    assert [n.key for n in outcome.missing] == ["browser"]
    assert "playwright install chromium" in out_of(c)


# -- AC-9: declining ----------------------------------------------------------------------------

def test_ac9_declining_the_only_required_item_exits_1_and_lists_what_is_missing(w, calls, monkeypatch):
    w.tier("fast")
    w.resume()
    w.profile()
    terminal(monkeypatch, Ask({Q_QUALITY: ["n"]}))
    res = CliRunner().invoke(cli.app, ["run", "tailor"])
    assert res.exit_code == 1, res.output
    text = flat(res.output)
    assert "Quality model" in text and "Fix: hireember models set quality" in text
    assert calls == []
    assert "quality" not in w.models.load_models_file(w.models_path)


def test_ac9_declining_an_item_only_an_optional_stage_needs_runs_the_others(w, calls, monkeypatch):
    w.tier("fast")
    w.resume()
    w.profile()
    terminal(monkeypatch, Ask({Q_QUALITY: ["n"]}))
    res = CliRunner().invoke(cli.app, ["run", "score", "tailor"])
    assert res.exit_code == 0, res.output
    text = flat(res.output)
    assert "Skipping tailor: quality model is not set up." in text
    assert len(calls) == 1 and stages_of(calls[0]) == ["score"]


def test_ac9_outcome_names_skipped_stages_and_their_reason(w, monkeypatch):
    w.tier("fast")
    w.resume()
    w.profile()
    preflight = terminal(monkeypatch, Ask({Q_QUALITY: ["n"]}))
    c = wide_console()
    outcome = preflight.run_preflight("run", ["score", "tailor", "cover"], console=c)
    assert outcome.proceed is True and outcome.stages == ["score"]
    assert set(outcome.skipped) >= {"tailor", "cover"}
    assert "Skipping tailor, cover: quality model is not set up." in out_of(c)
    assert [n.key for n in outcome.missing] == ["quality_tier"]


def test_ac9_a_stage_is_never_run_partially_when_its_input_is_missing(w, monkeypatch):
    w.tier("fast")
    w.profile()
    w.search()
    preflight = terminal(monkeypatch, Ask({Q_RESUME: ["n"]}))
    outcome = preflight.run_preflight("run", ["discover", "score"], console=wide_console())
    assert "discover" in outcome.stages
    assert "score" not in outcome.stages
    assert "score" in outcome.skipped


@pytest.mark.parametrize("reply", [KeyboardInterrupt, EOFError])
def test_ctrl_c_and_ctrl_d_decline_everything_without_a_traceback(w, calls, monkeypatch, reply):
    w.tier("fast")
    w.resume()
    w.profile()
    terminal(monkeypatch, Ask({Q_QUALITY: [reply]}))
    res = CliRunner().invoke(cli.app, ["run", "tailor"])
    assert res.exit_code == 1
    assert not isinstance(res.exception, (KeyboardInterrupt, EOFError))
    assert res.exception is None or isinstance(res.exception, SystemExit)
    assert "Traceback" not in res.output
    assert calls == []


@pytest.mark.parametrize("question, which, stages", [
    (Q_PROFILE, "profile", ["score"]),
    (Q_SEARCH, "search", ["discover"]),
])
def test_profile_and_search_config_are_offered_and_declining_stops_the_run(w, monkeypatch, question, which, stages):
    w.tier("fast")
    w.resume()
    if which != "profile":
        w.profile()
    else:
        w.search()
    ask = Ask({question: ["n"]})
    preflight = terminal(monkeypatch, ask)
    outcome = preflight.run_preflight("run", stages, console=wide_console())
    assert ask.log == [question]
    assert outcome.proceed is False


def test_install_only_items_are_never_prompted(w, monkeypatch):
    w.search(["indeed"])
    w.block_jobspy()
    preflight = terminal(monkeypatch, NeverAsk())
    c = wide_console()
    outcome = preflight.run_preflight("run", ["discover"], console=c)
    assert outcome.proceed is False
    text = out_of(c)
    assert "python-jobspy" in text and "-m pip install -e ." in text


def test_ac13_no_key_value_appears_anywhere_in_a_full_interactive_session(w, monkeypatch):
    w.resume()
    w.profile()
    ask = Ask({Q_FAST: ["y"], Q_PROVIDER: ["openai"], Q_MODEL: ["gpt-x"], Q_KEY: [SECRET],
               Q_QUALITY: ["y"], Q_SAME: ["y"]})
    preflight = terminal(monkeypatch, ask)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["score", "tailor"], console=c)
    assert outcome.proceed is True
    assert SECRET not in c.file.getvalue()
    assert w.models.load_models_file(w.models_path)["quality"]["api_key"] == SECRET
