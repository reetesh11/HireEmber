"""AC-3: every LLM call site requests a tier by name (fast or quality)."""

import json

from p0e_helpers import FakeClient

JOB = {"title": "Python Dev", "site": "Acme", "location": "Toronto", "full_description": "Build services."}
PROFILE = {
    "skills_boundary": {"languages": ["Python"]},
    "resume_facts": {"preserved_companies": ["Company A"], "preserved_projects": ["Project X"],
                     "preserved_school": "Your University", "real_metrics": []},
}
GOOD = {
    "title": "Dev", "summary": "Builds services.", "skills": {"Languages": "Python"},
    "experience": [{"header": "Company A", "subtitle": "2020", "bullets": ["Built APIs."]}],
    "projects": [{"header": "Project X", "subtitle": "Python", "bullets": ["Parsed logs."]}],
    "education": "Your University | BSc",
}


class Recorder:
    """A get_client stand-in that requires its tier argument and records it."""

    def __init__(self, reply="SCORE: 8\nKEYWORDS: a\nREASONING: Fine."):
        self.tiers: list[str] = []
        self.reply = reply

    def __call__(self, tier):
        self.tiers.append(tier)
        return FakeClient(self.reply)


def _attempt(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except Exception:  # only the requested tier matters here
        pass


def test_scoring_requests_fast(monkeypatch):
    from hireember.scoring import scorer

    rec = Recorder()
    monkeypatch.setattr(scorer, "get_client", rec)
    result = scorer.score_job("RESUME", JOB, {})
    assert rec.tiers == ["fast"]
    assert result["score"] == 8


def test_tailoring_and_judge_request_quality(monkeypatch):
    from hireember.scoring import tailor

    rec = Recorder(json.dumps(GOOD))
    monkeypatch.setattr(tailor, "get_client", rec)
    _attempt(tailor.tailor_resume, "RESUME", JOB, PROFILE, max_retries=0, validation_mode="lenient")
    assert rec.tiers and set(rec.tiers) == {"quality"}

    rec.tiers.clear()
    monkeypatch.setattr(tailor, "get_client", rec)
    _attempt(tailor.judge_tailored_resume, "RESUME", "TAILORED", "Dev", PROFILE)
    assert rec.tiers and set(rec.tiers) == {"quality"}


def test_cover_letter_requests_quality(monkeypatch):
    from hireember.scoring import cover_letter

    rec = Recorder("Dear Hiring Manager,\n\nHello.")
    monkeypatch.setattr(cover_letter, "get_client", rec)
    _attempt(cover_letter.generate_cover_letter, "RESUME", JOB, PROFILE, max_retries=0,
             validation_mode="lenient")
    assert rec.tiers and set(rec.tiers) == {"quality"}


def test_smart_extract_requests_fast(monkeypatch):
    from hireember.discovery import smartextract

    rec = Recorder('{"relevant": true, "reason": "jobs"}')
    monkeypatch.setattr(smartextract, "get_client", rec)
    smartextract.ask_llm("extract jobs")
    assert rec.tiers == ["fast"]

    rec.tiers.clear()
    _attempt(smartextract.judge_api_responses,
             [{"type": "json", "url": "http://x/api", "first_item_keys": ["title"], "sample": "{}"}])
    assert rec.tiers and set(rec.tiers) == {"fast"}


def test_detail_enrichment_extraction_requests_fast(monkeypatch):
    from hireember.enrichment import detail

    class Page:
        def query_selector(self, selector):
            return None

        def evaluate(self, script):
            return "<div><p>" + "Real job description text. " * 30 + "</p></div>"

        def title(self):
            return "Job"

    rec = Recorder('{"full_description": "Long text", "application_url": null}')
    monkeypatch.setattr(detail, "get_client", rec)
    detail.extract_with_llm(Page(), "http://x/job")
    assert rec.tiers == ["fast"]


def test_gate_flow_uses_fast_then_quality(monkeypatch, tmp_path, isolated_db):
    from hireember import config, gating
    from hireember.database import init_db, store_jobs
    from hireember.resumes import add_resume
    from hireember.scoring import cover_letter, scorer, tailor

    conn = init_db(isolated_db)
    config.ensure_dirs()
    store_jobs(conn, [{"url": "u1", "title": "Python Dev", "company": "Acme", "location": "Toronto, ON"}], "S", "t")
    conn.execute("UPDATE jobs SET full_description = 'desc'")
    conn.commit()
    f = tmp_path / "r.txt"
    f.write_text("RESUME")
    add_resume(conn, f, "Base", "python")

    order: list[str] = []

    def make(reply):
        def get(tier):
            order.append(tier)
            return FakeClient(reply)
        return get

    monkeypatch.setattr(scorer, "get_client", make("SCORE: 9\nKEYWORDS: a\nREASONING: Great."))
    monkeypatch.setattr(tailor, "get_client", make(json.dumps(GOOD)))
    monkeypatch.setattr(cover_letter, "get_client", make("Dear Hiring Manager,\n\nHello."))
    profile = dict(PROFILE, personal={"city": "Toronto", "province_state": "Ontario", "country": "Canada"})
    _attempt(gating.process_job, conn, "u1", profile=profile, validation_mode="lenient")
    assert order[0] == "fast"
    assert "quality" in order
    assert set(order) <= {"fast", "quality"}
    assert order.index("quality") > order.index("fast")
