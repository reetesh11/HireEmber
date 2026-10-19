import io

from rich.console import Console

from hireember import config, models, pipeline


def test_summary_lists_models_for_executed_stages_only(monkeypatch, tmp_path, isolated_db):
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "MODELS_PATH", tmp_path / "models.toml")
    models.save_tier("fast", provider="custom", model="small", base_url="http://localhost:1/v1")
    models.save_tier("quality", provider="custom", model="big", base_url="http://localhost:1/v1")
    buf = io.StringIO()
    monkeypatch.setattr(pipeline, "console", Console(file=buf, width=200))
    pipeline.run_pipeline(stages=["score"])
    out = buf.getvalue()
    assert "scoring: small (fast)" in out
    assert "big" not in out
