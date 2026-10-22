"""AC-8, AC-10, AC-11, AC-12, AC-13, AC-14, AC-15, AC-17: detection, report, non-interactive and skipped cases."""

import pytest
from p0f_helpers import (
    ALL_STAGES,
    LOCAL,
    SECRET,
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
    """Record the stage runs and apply launches the CLI would start."""
    rec = {"pipeline": [], "apply": [], "mark": []}

    def fake_pipeline(*args, **kwargs):
        rec["pipeline"].append((args, kwargs))
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    monkeypatch.setattr("hireember.pipeline.run_pipeline", fake_pipeline)
    monkeypatch.setattr("hireember.apply.launcher.main", lambda *a, **k: rec["apply"].append((a, k)))
    monkeypatch.setattr("hireember.apply.launcher.mark_job", lambda *a, **k: rec["mark"].append((a, k)))
    monkeypatch.setattr("hireember.apply.launcher.reset_failed", lambda *a, **k: rec["mark"].append((a, k)) or 0)
    return rec


def stages_of(call):
    args, kwargs = call
    return kwargs.get("stages", args[0] if args else None)


def invoke(*args):
    return CliRunner().invoke(cli.app, list(args))


def keys(needs):
    return [n.key for n in needs]


# -- detection (find_needs) -------------------------------------------------------------------

def test_ac10_run_discover_never_mentions_models_even_when_both_tiers_missing(w, monkeypatch):
    from hireember import preflight

    w.search()
    needs, warnings = preflight.find_needs("run", ["discover"])
    assert keys(needs) == [] and warnings == []
    assert w.probed == []


def test_ac10_run_score_looks_at_the_fast_tier_only(w):
    from hireember import preflight

    w.resume()
    w.profile()
    needs, _ = preflight.find_needs("run", ["score"])
    assert keys(needs) == ["fast_tier"]
    assert needs[0].title == "Fast model" and needs[0].stages == ("score",)
    assert needs[0].fix == "hireember models set fast" and needs[0].fixable is True


@pytest.mark.parametrize("stages", [["tailor", "cover"], ["tailor"], ["cover"]])
def test_ac10_run_tailor_cover_look_at_the_quality_tier_only(w, stages):
    from hireember import preflight

    w.resume()
    w.profile()
    needs, _ = preflight.find_needs("run", stages)
    assert keys(needs) == ["quality_tier"]
    assert needs[0].title == "Quality model" and set(needs[0].stages) == set(stages)
    assert needs[0].fix == "hireember models set quality"


def test_ac10_run_enrich_asks_only_about_the_browser(w):
    from hireember import preflight

    w.browser_installed = False
    needs, _ = preflight.find_needs("run", ["enrich"])
    assert keys(needs) == ["browser"]
    assert needs[0].title == "Playwright browser" and needs[0].fix == "playwright install chromium"


def test_pdf_needs_nothing(w):
    from hireember import preflight

    w.browser_installed = False
    needs, _ = preflight.find_needs("run", ["pdf"])
    assert needs == []


def test_ac17_a_shared_need_is_listed_once_naming_every_stage(w):
    from hireember import preflight

    w.tier("fast")
    w.tier("quality")
    w.profile()
    needs, _ = preflight.find_needs("run", ["score", "tailor"])
    assert keys(needs) == ["resume"]
    assert set(needs[0].stages) == {"score", "tailor"}
    assert needs[0].fix == "hireember resume add <file> --name <name>"


def test_all_is_expanded_and_needs_come_in_the_fixed_order(w):
    from hireember import preflight

    w.search(["indeed"])
    w.block_jobspy()
    w.browser_installed = False
    needs, _ = preflight.find_needs("run", ["all"])
    assert keys(needs) == ["jobspy", "fast_tier", "quality_tier", "resume", "profile", "browser"]
    needs2, _ = preflight.find_needs("run", ALL_STAGES)
    assert keys(needs2) == keys(needs)


def test_missing_search_config_is_a_need_for_discover(w):
    from hireember import preflight

    needs, _ = preflight.find_needs("run", ["discover"])
    assert "search_config" in keys(needs)
    assert "Search config" == next(n.title for n in needs if n.key == "search_config")


def test_jobspy_is_needed_only_when_a_job_board_is_configured(w):
    from hireember import preflight

    w.block_jobspy()
    w.search([])
    assert "jobspy" not in keys(preflight.find_needs("run", ["discover"])[0])
    w.search(["indeed"])
    needs, _ = preflight.find_needs("run", ["discover"])
    jobspy = next(n for n in needs if n.key == "jobspy")
    assert jobspy.title == "python-jobspy" and jobspy.fixable is False
    assert "-m pip install -e ." in jobspy.fix


def test_resume_registered_but_text_file_missing_is_a_missing_resume(w):
    from hireember import preflight

    w.tier("fast")
    w.profile()
    w.resume(text=False, registered=True)
    assert keys(preflight.find_needs("run", ["score"])[0]) == ["resume"]


def test_resume_text_file_present_but_nothing_registered_is_a_missing_resume(w):
    from hireember import preflight

    w.tier("fast")
    w.profile()
    w.resume(text=True, registered=False)
    assert keys(preflight.find_needs("run", ["score"])[0]) == ["resume"]


def test_missing_profile_is_a_need_for_score_and_apply(w):
    from hireember import preflight

    w.tier("fast")
    w.resume()
    needs, _ = preflight.find_needs("run", ["score"])
    assert keys(needs) == ["profile"] and needs[0].title == "Profile" and needs[0].fix == "hireember init"


def test_malformed_models_file_is_listed_as_a_missing_tier(w):
    from hireember import preflight

    w.resume()
    w.profile()
    w.models_path.write_text("[fast\nprovider = ", encoding="utf-8")
    needs, _ = preflight.find_needs("run", ["score"])
    assert keys(needs) == ["fast_tier"]


def test_unreachable_tier_is_a_warning_not_a_need(w):
    from hireember import preflight

    w.everything()
    w.probe_ok = False
    needs, warnings = preflight.find_needs("run", ["score"])
    assert needs == []
    assert len(warnings) == 1
    assert w.probed == ["fast"]


def test_ac14_the_check_makes_no_llm_call(w, monkeypatch):
    from hireember import preflight

    def boom(*a, **k):
        raise AssertionError("the settings check must not request a completion")

    monkeypatch.setattr("hireember.llm.LLMClient.chat", boom)
    monkeypatch.setattr("hireember.models.test_tier", boom)
    w.everything()
    w.browser_installed = False
    preflight.find_needs("run", ALL_STAGES)
    preflight.run_preflight("run", ALL_STAGES, no_prompt=True, console=wide_console())


# -- apply needs ------------------------------------------------------------------------------

def test_ac11_apply_needs_claude_chrome_with_install_pointers_and_not_prompted(w):
    from hireember import preflight

    w.profile()
    w.tailored()
    w.chrome_installed = False
    needs, _ = preflight.find_needs("apply", [], conn=w.conn)
    assert keys(needs) == ["claude", "chrome"]
    claude, chrome = needs
    assert claude.title == "Claude Code CLI" and "https://claude.ai/code" in claude.fix
    assert chrome.title == "Chrome"
    assert claude.fixable is False and chrome.fixable is False


def test_apply_with_no_tailored_resumes_lists_them_and_is_not_fixable(w):
    from hireember import preflight

    w.profile()
    w.claude()
    needs, _ = preflight.find_needs("apply", [], conn=w.conn)
    assert keys(needs) == ["tailored"]
    assert needs[0].title == "Tailored resumes" and needs[0].fixable is False
    assert "hireember run score tailor" in needs[0].fix or "hireember run score tailor" in needs[0].detail


def test_apply_with_gen_url_does_not_check_tailored_resumes(w):
    from hireember import preflight

    w.profile()
    w.claude()
    assert preflight.find_needs("apply", [], conn=w.conn, gen_url=True)[0] == []


def test_apply_missing_profile_is_a_need(w):
    from hireember import preflight

    w.claude()
    w.tailored()
    assert keys(preflight.find_needs("apply", [], conn=w.conn)[0]) == ["profile"]


# -- report -----------------------------------------------------------------------------------

def test_report_shape_for_several_items(w):
    from hireember import preflight

    w.tier("fast")
    w.profile()
    w.browser_installed = False
    needs, warnings = preflight.find_needs("run", ["enrich", "tailor"])
    text = flat(preflight.format_report(needs, warnings, interactive=True))
    assert "Before this run can start, 3 things need setting up:" in text
    assert text.index("Quality model") < text.index("Base resume") < text.index("Playwright browser")
    assert "(used by tailor)" in text and "(used by enrich)" in text
    assert "Fix: hireember models set quality" in text
    assert "Fix: hireember resume add <file> --name <name>" in text
    assert "Fix: playwright install chromium" in text
    assert "No base resume is registered, or its text file is missing." in text
    assert "Run again after fixing these" not in text


def test_report_single_item_uses_singular_and_noninteractive_ending(w):
    from hireember import preflight

    w.tier("fast")
    w.profile()
    w.resume()
    needs, warnings = preflight.find_needs("run", ["tailor", "cover"])
    text = flat(preflight.format_report(needs, warnings, interactive=False))
    assert "Before this run can start, 1 thing need setting up:" in text or \
        "Before this run can start, 1 thing needs setting up:" in text
    assert "(used by tailor, cover)" in text
    assert text.rstrip().endswith("Run again after fixing these, or run in a terminal to be prompted.")


# -- run_preflight without prompting -----------------------------------------------------------

def test_nothing_missing_prints_nothing_and_proceeds_with_all_stages(w, monkeypatch):
    from hireember import preflight

    w.everything()
    ask = NeverAsk()
    monkeypatch.setattr(preflight, "ask_user", ask)
    monkeypatch.setattr(preflight, "is_interactive", lambda: True)
    c = wide_console()
    outcome = preflight.run_preflight("run", ALL_STAGES, console=c)
    assert outcome.proceed is True
    assert outcome.stages == ALL_STAGES and outcome.skipped == {} and outcome.missing == []
    assert out_of(c) == "" and ask.log == []


@pytest.mark.parametrize("interactive, no_prompt", [(False, False), (True, True), (False, True)])
def test_ac8_no_terminal_or_no_prompt_lists_and_never_asks(w, monkeypatch, interactive, no_prompt):
    from hireember import preflight

    w.tier("fast")
    w.resume()
    w.profile()
    ask = NeverAsk()
    monkeypatch.setattr(preflight, "ask_user", ask)
    monkeypatch.setattr(preflight, "is_interactive", lambda: interactive)
    c = wide_console()
    outcome = preflight.run_preflight("run", ["tailor"], no_prompt=no_prompt, console=c)
    assert outcome.proceed is False
    assert keys(outcome.missing) == ["quality_tier"]
    text = out_of(c)
    assert "Before this run can start, 1 thing" in text and "Quality model" in text
    assert "Fix: hireember models set quality" in text
    assert text.endswith("Run again after fixing these, or run in a terminal to be prompted.")
    assert ask.log == []


@pytest.mark.parametrize("args", [["run", "tailor"], ["run", "tailor", "--no-prompt"]])
def test_ac8_cli_exits_1_lists_and_starts_nothing(w, calls, monkeypatch, args):
    from hireember import preflight

    w.tier("fast")
    w.resume()
    w.profile()
    monkeypatch.setattr(preflight, "ask_user", NeverAsk())
    before = w.models_path.read_text(encoding="utf-8")
    res = invoke(*args)
    assert res.exit_code == 1, res.output
    text = flat(res.output)
    assert "Quality model" in text and "Fix: hireember models set quality" in text
    assert "Run again after fixing these, or run in a terminal to be prompted." in text
    assert calls["pipeline"] == []
    assert w.models_path.read_text(encoding="utf-8") == before


def test_ac8_with_nothing_missing_no_prompt_changes_nothing(w, calls, monkeypatch):
    from hireember import preflight

    w.everything()
    monkeypatch.setattr(preflight, "ask_user", NeverAsk())
    res = invoke("run", "score", "--no-prompt")
    assert res.exit_code == 0, res.output
    assert "need setting up" not in res.output and "Before this run" not in res.output
    assert len(calls["pipeline"]) == 1
    assert stages_of(calls["pipeline"][0]) in (["score"], ("score",))


def test_ac8_cli_does_not_wait_on_input_without_a_terminal(w, calls):
    w.tier("fast")
    res = CliRunner().invoke(cli.app, ["run", "score"], input="")
    assert res.exit_code == 1
    assert calls["pipeline"] == []


# -- apply through the CLI ----------------------------------------------------------------------

@pytest.mark.parametrize("interactive", [False, True])
def test_ac11_cli_apply_lists_claude_and_chrome_without_prompting(w, calls, monkeypatch, interactive):
    from hireember import preflight

    w.profile()
    w.tailored()
    w.chrome_installed = False
    monkeypatch.setattr(preflight, "is_interactive", lambda: interactive)
    monkeypatch.setattr(preflight, "ask_user", NeverAsk())
    res = invoke("apply")
    assert res.exit_code == 1, res.output
    text = flat(res.output)
    assert "Claude Code CLI" in text and "https://claude.ai/code" in text
    assert "Chrome" in text and "2 things" in text
    assert calls["apply"] == []


def test_apply_with_everything_present_launches(w, calls, monkeypatch):
    from hireember import preflight

    w.everything()
    monkeypatch.setattr(preflight, "ask_user", NeverAsk())
    res = invoke("apply", "--no-prompt")
    assert res.exit_code == 0, res.output
    assert "Before this run" not in res.output
    assert len(calls["apply"]) == 1


# -- help ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["run", "apply"])
def test_ac15_no_prompt_flag_is_in_help(command):
    res = CliRunner().invoke(cli.app, [command, "--help"])
    assert res.exit_code == 0
    text = flat(res.output.replace("\u2502", " "))  # help cells wrap inside box borders
    assert "--no-prompt" in text
    assert "Never prompt; list missing settings and exit 1." in text


# -- secrets ------------------------------------------------------------------------------------

def test_ac13_key_values_are_not_in_reports(w, monkeypatch):
    from hireember import preflight

    w.tier("fast", provider="openai", model="gpt-x", base_url=None, api_key=SECRET)
    w.resume()
    w.profile()
    needs, warnings = preflight.find_needs("run", ["score", "tailor"])
    text = preflight.format_report(needs, warnings, interactive=False)
    assert SECRET not in text and SECRET not in repr(needs) and SECRET not in repr(warnings)
    assert LOCAL not in text
