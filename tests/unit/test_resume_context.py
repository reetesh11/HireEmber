"""Retrieval context in prompts (implementation tests)."""

import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.resumes import add_resume, context_block
from hireember.tickets import set_setting

HEADER = "RELEVANT RESUME EXCERPTS (best matches for this job):\n"
JOB = {"title": "Python Engineer", "full_description": "Python and SQL"}


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    config.ensure_dirs()
    yield c
    close_connection(db)


def _resume(conn, tmp_path, text):
    p = tmp_path / "r.txt"
    p.write_text(text, encoding="utf-8")
    return add_resume(conn, p, "R")


def test_block_format_and_n(conn, tmp_path):
    rid = _resume(conn, tmp_path, "Experience\n" + "\n\n".join(f"Python job {i} " + "x " * 200 for i in range(6)))
    block = context_block(conn, rid, JOB)
    assert block.startswith(HEADER) and len(block[len(HEADER):].split("\n")) == 5
    set_setting(conn, "resume_context_chunks", "2")
    assert len(context_block(conn, rid, JOB)[len(HEADER):].split("\n")) == 2
    assert context_block(conn, rid, {"title": "zzz"}) == ""


def test_scorer_message_unchanged_when_empty(monkeypatch):
    from hireember.scoring import scorer

    seen = []

    class Client:
        def chat(self, messages, **kw):
            seen.append(messages[1]["content"])
            return "SCORE: 5\nKEYWORDS: a\nREASONING: b"

    monkeypatch.setattr(scorer, "get_client", lambda *a, **k: Client())
    job = {"title": "T", "site": "S", "full_description": "d"}
    scorer.score_job("R", job)
    scorer.score_job("R", job, resume_context="")
    scorer.score_job("R", job, resume_context="CTX")
    assert seen[0] == seen[1]
    assert seen[2].startswith("RESUME:\nR\n\n---\n\nCTX\n\n---\n\n")
