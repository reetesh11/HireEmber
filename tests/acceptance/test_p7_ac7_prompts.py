"""Phase 7 AC-7: retrieved chunks reach the scoring, tailoring and apply prompts."""

import json

import pytest

from p2_helpers import install_fake_llm, profile, store_job
from p7_helpers import REPO_ROOT, text_file

HEADER = "RELEVANT RESUME EXCERPTS (best matches for this job):\n"
JOB = {"title": "Python Backend Engineer", "site": "Acme", "location": "Berlin",
       "full_description": "Build Python APIs with FastAPI and SQL."}
MANY = "Experience\n" + "\n\n".join(
    f"Project {i}: Python service number {i}. " + ("detail " * 70) for i in range(10))


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def _resume(conn, tmp_path, name, text):
    from hireember.resumes import add_resume

    return add_resume(conn, text_file(tmp_path, text), name)


# -- context_block -----------------------------------------------------------

def test_context_block_format(conn, tmp_path):
    from hireember.resumes import context_block

    rid = _resume(conn, tmp_path, "Fmt", "Experience\nBuilt Python APIs\nwith FastAPI.\n\nSkills\nGardening")
    block = context_block(conn, rid, JOB)
    assert block.startswith(HEADER)
    assert not block.endswith("\n")
    lines = block[len(HEADER):].split("\n")
    assert lines and all(ln.startswith("[") for ln in lines)
    assert lines[0].startswith("[experience] ")
    assert "Built Python APIs with FastAPI." in lines[0]  # newlines collapsed to spaces


def test_context_block_default_is_five_chunks(conn, tmp_path):
    from hireember.resumes import context_block

    rid = _resume(conn, tmp_path, "Many", MANY)
    assert len(context_block(conn, rid, JOB)[len(HEADER):].split("\n")) == 5


def test_context_block_n_argument_and_setting(conn, tmp_path):
    from hireember.resumes import context_block
    from hireember.tickets import set_setting

    rid = _resume(conn, tmp_path, "Many", MANY)
    assert len(context_block(conn, rid, JOB, n=2)[len(HEADER):].split("\n")) == 2
    set_setting(conn, "resume_context_chunks", "3")
    assert len(context_block(conn, rid, JOB)[len(HEADER):].split("\n")) == 3
    set_setting(conn, "resume_context_chunks", "banana")
    assert len(context_block(conn, rid, JOB)[len(HEADER):].split("\n")) == 5
    set_setting(conn, "resume_context_chunks", "0")
    assert len(context_block(conn, rid, JOB)[len(HEADER):].split("\n")) == 5


def test_context_block_empty_when_no_chunks_or_no_match(conn, tmp_path):
    from hireember.resume_index import delete_chunks
    from hireember.resumes import context_block

    rid = _resume(conn, tmp_path, "Plain", "Skills\nGardening and cooking")
    assert context_block(conn, rid, {"title": "Quantum Astrophysicist", "full_description": ""}) == ""
    delete_chunks(conn, rid)
    assert context_block(conn, rid, JOB) == ""


def test_context_block_only_uses_the_given_resume(conn, tmp_path):
    from hireember.resumes import context_block

    a = _resume(conn, tmp_path, "A", "Skills\nPython from resume A")
    _resume(conn, tmp_path, "B", "Skills\nPython from resume B")
    block = context_block(conn, a, JOB)
    assert "resume A" in block and "resume B" not in block


# -- scorer / tailor / build_prompt hooks -----------------------------------

def _capture(monkeypatch, module, reply):
    seen = []

    class Client:
        def chat(self, messages, max_tokens=None, temperature=None):
            seen.append(messages)
            return reply

    monkeypatch.setattr(f"hireember.scoring.{module}.get_client", lambda *a, **k: Client())
    return seen


def test_score_job_inserts_context_between_resume_and_job(monkeypatch):
    from hireember.scoring import scorer

    seen = _capture(monkeypatch, "scorer", "SCORE: 7\nKEYWORDS: a\nREASONING: ok")
    scorer.score_job("BASE TEXT", JOB, None)
    scorer.score_job("BASE TEXT", JOB, None, resume_context="CTX-BLOCK")
    plain, with_ctx = seen[0][1]["content"], seen[1][1]["content"]
    assert with_ctx.startswith("RESUME:\nBASE TEXT\n\n---\n\nCTX-BLOCK\n\n---\n\n")
    assert with_ctx == plain.replace("\n\n---\n\n", "\n\n---\n\nCTX-BLOCK\n\n---\n\n", 1)
    assert seen[1][0] == seen[0][0]


def test_tailor_resume_inserts_context(monkeypatch):
    from hireember.scoring import tailor

    from p2_helpers import tailor_json

    seen = _capture(monkeypatch, "tailor", json.dumps(tailor_json()))
    tailor.tailor_resume("BASE TEXT", JOB, profile(), max_retries=0, validation_mode="lenient")
    tailor.tailor_resume("BASE TEXT", JOB, profile(), max_retries=0, validation_mode="lenient",
                         resume_context="CTX-BLOCK")
    plain, with_ctx = seen[0][1]["content"], seen[1][1]["content"]
    assert with_ctx.startswith("ORIGINAL RESUME:\nBASE TEXT\n\n---\n\nCTX-BLOCK\n\n---\n\nTARGET JOB:")
    assert with_ctx == plain.replace("\n\n---\n\n", "\n\n---\n\nCTX-BLOCK\n\n---\n\n", 1)


@pytest.fixture
def prompt_builder(tmp_path, monkeypatch):
    import hireember.config as config
    from hireember.apply.prompt import build_prompt

    prof = json.loads((REPO_ROOT / "profile.example.json").read_text(encoding="utf-8"))
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(prof), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    monkeypatch.setattr(config, "APPLY_WORKER_DIR", tmp_path / "workers")
    resume = tmp_path / "r.txt"
    resume.write_text("x")
    resume.with_suffix(".pdf").write_bytes(b"%PDF-1.4")
    job = {"url": "https://j/1", "title": "Eng", "site": "Acme", "tailored_resume_path": str(resume)}
    return lambda **kw: build_prompt(job, "TAILORED BODY", **kw)


def test_build_prompt_inserts_excerpts_after_resume_text(prompt_builder):
    plain = prompt_builder()
    with_ctx = prompt_builder(resume_context="CTX-BLOCK")
    block = "== RESUME EXCERPTS (from your base resume, reference only) ==\nCTX-BLOCK\n\n"
    assert block in with_ctx
    assert with_ctx.index("TAILORED BODY") < with_ctx.index(block) < with_ctx.index("== COVER LETTER TEXT")
    assert with_ctx.replace(block, "", 1) == plain
    assert prompt_builder(resume_context="") == plain


# -- wired through gating ----------------------------------------------------

def test_scoring_and_tailoring_prompts_carry_chunks(conn, tmp_path, monkeypatch):
    from hireember.gating import process_job

    _resume(conn, tmp_path, "Backend", "Experience\nBuilt Python APIs with FastAPI at Acme.\n\nSkills\nGardening")
    fake = install_fake_llm(monkeypatch, score=8)
    res = process_job(conn, store_job(conn, "https://j.example/ctx"), profile=profile(),
                      validation_mode="lenient")
    assert res.status == "pending"
    scorer_msg = fake.calls["scorer"][0][1]["content"]
    tailor_msg = fake.calls["tailor"][0][1]["content"]
    for msg in (scorer_msg, tailor_msg):
        assert HEADER in msg
        assert "[experience] Built Python APIs with FastAPI at Acme." in msg
    assert scorer_msg.index(HEADER) < scorer_msg.index("JOB POSTING:")
    assert tailor_msg.index(HEADER) < tailor_msg.index("TARGET JOB:")


def test_context_comes_from_the_resume_used_for_the_ticket(conn, tmp_path, monkeypatch):
    from hireember.gating import score_job_for_ticket
    from hireember.resumes import pin_resume

    _resume(conn, tmp_path, "Front", "Skills\nPython only in the front resume")
    back = _resume(conn, tmp_path, "Back", "Skills\nPython only in the back resume")
    pin_resume(conn, back)
    fake = install_fake_llm(monkeypatch, score=8)
    score_job_for_ticket(conn, store_job(conn, "https://j.example/which"), profile=profile())
    msg = fake.calls["scorer"][0][1]["content"]
    excerpts = msg[msg.index(HEADER):msg.index("JOB POSTING:")]
    assert "back resume" in excerpts and "front resume" not in excerpts


def test_resume_without_chunks_adds_no_block(conn, tmp_path, monkeypatch):
    from hireember.gating import process_job
    from hireember.resume_index import delete_chunks

    rid = _resume(conn, tmp_path, "Backend", "Experience\nBuilt Python APIs.")
    delete_chunks(conn, rid)
    fake = install_fake_llm(monkeypatch, score=8)
    process_job(conn, store_job(conn, "https://j.example/nochunks"), profile=profile(), validation_mode="lenient")
    assert "RELEVANT RESUME EXCERPTS" not in fake.texts("scorer")
    assert "RELEVANT RESUME EXCERPTS" not in fake.texts("tailor")

