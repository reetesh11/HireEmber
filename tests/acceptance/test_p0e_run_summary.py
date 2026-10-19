"""AC-17: the run summary lists which model did what."""

import pytest
from p0e_helpers import isolate_models, write_models
from rich.console import Console

LOCAL = "http://localhost:11434/v1"


@pytest.fixture
def path(monkeypatch, tmp_path):
    return isolate_models(monkeypatch, tmp_path)


def test_stage_model_lines_with_legacy_env(path, monkeypatch):
    from hireember import models

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    lines = models.stage_model_lines(["discover", "enrich", "score", "tailor", "cover", "pdf"])
    assert lines == [
        "discovery: gemini-2.0-flash (fast)",
        "enrichment: gemini-2.0-flash (fast)",
        "scoring: gemini-2.0-flash (fast)",
        "tailoring: gemini-2.0-flash (quality)",
        "cover letters: gemini-2.0-flash (quality)",
    ]


def test_stage_model_lines_distinct_tiers_and_only_executed_stages(path, monkeypatch):
    from hireember import models

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    write_models(path, f'[quality]\nprovider = "custom"\nmodel = "llama3.1:70b"\nbase_url = "{LOCAL}"\n')
    assert models.stage_model_lines(["score", "tailor"]) == [
        "scoring: gemini-2.0-flash (fast)",
        "tailoring: llama3.1:70b (quality)",
    ]
    assert models.stage_model_lines(["pdf"]) == []
    assert models.stage_model_lines([]) == []


def test_unconfigured_tier_stage_is_omitted(path):
    from hireember import models

    write_models(path, f'[fast]\nprovider = "custom"\nmodel = "small"\nbase_url = "{LOCAL}"\n')
    assert models.stage_model_lines(["score", "tailor", "cover"]) == ["scoring: small (fast)"]


def test_run_pipeline_prints_model_line_for_executed_stage(path, monkeypatch, isolated_db):
    import io

    from hireember import pipeline

    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    buf = io.StringIO()
    monkeypatch.setattr(pipeline, "console", Console(file=buf, width=300))
    pipeline.run_pipeline(stages=["score"])
    out = buf.getvalue()
    assert "Pipeline Summary" in out
    assert "scoring: gemini-2.0-flash (fast)" in out
    assert "tailoring:" not in out
    assert out.index("Pipeline Summary") < out.index("scoring: gemini-2.0-flash (fast)")
