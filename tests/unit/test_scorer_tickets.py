import pytest

from hireember import config
from hireember.database import close_connection, init_db, store_jobs
from hireember.resumes import add_resume
from hireember.scoring import scorer
from hireember.tickets import get_ticket_by_url


@pytest.fixture
def conn(tmp_path, monkeypatch):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    store_jobs(c, [{"url": "u7", "title": "A"}, {"url": "u3", "title": "B"}], "S", "t")
    c.execute("UPDATE jobs SET full_description = 'desc'")
    c.commit()
    resume = tmp_path / "resume.txt"
    resume.write_text("resume")
    config.ensure_dirs()
    add_resume(c, resume, "Base")
    monkeypatch.setattr(scorer, "get_connection", lambda: c)
    yield c
    close_connection(db)


def test_run_scoring_creates_tickets(conn, monkeypatch):
    scores = {"u7": 7, "u3": 3}
    monkeypatch.setattr(
        scorer, "score_job",
        lambda resume, job, profile=None: {"score": scores[job["url"]], "keywords": "kw", "reasoning": "why"},
    )
    result = scorer.run_scoring()
    assert result["scored"] == 2
    assert get_ticket_by_url(conn, "u7")["status"] == "pending"
    assert get_ticket_by_url(conn, "u3")["status"] == "skipped"
    row = conn.execute("SELECT fit_score, score_reasoning, scored_at FROM jobs WHERE url='u7'").fetchone()
    assert row["fit_score"] == 7 and row["score_reasoning"] == "why" and row["scored_at"]
