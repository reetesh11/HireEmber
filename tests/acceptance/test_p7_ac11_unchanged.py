"""Phase 7 AC-11 (and the unchanged part of AC-7): existing resume behaviour and prompts are unchanged.

Covers name uniqueness, pin, unpin, choose-best-resume, text lookup, and byte-identical prompts for a
resume that has no chunks.
"""

import json
import uuid

import pytest

from p2_helpers import install_fake_llm, profile, store_job
from p7_helpers import REPO_ROOT, base_dir, blank_pdf_bytes, text_file


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_name_uniqueness_is_case_and_space_insensitive(conn, tmp_path):
    from hireember.resumes import ResumeError, add_resume, update_resume_meta

    a = add_resume(conn, text_file(tmp_path), "Backend")
    b = add_resume(conn, text_file(tmp_path), "Frontend")
    with pytest.raises(ResumeError) as exc:
        add_resume(conn, text_file(tmp_path), "  backend ")
    assert str(exc.value) == 'A resume named "  backend " already exists.'
    with pytest.raises(ResumeError) as exc:
        update_resume_meta(conn, b, name="BACKEND")
    assert str(exc.value) == 'A resume named "BACKEND" already exists.'
    update_resume_meta(conn, a, name="Backend 2", tags="Python, python, Go")
    from hireember.resumes import list_resumes
    row = [r for r in list_resumes(conn) if r["id"] == a][0]
    assert row["name"] == "Backend 2" and row["tags"] == ["python", "go"]


def test_pin_unpin_and_choose(conn, tmp_path):
    from hireember.resumes import ResumeError, add_resume, choose_resume, list_resumes, pin_resume, unpin_resume

    front = add_resume(conn, text_file(tmp_path), "Front", "frontend,react")
    back = add_resume(conn, text_file(tmp_path), "Back", "backend,python")
    job = {"title": "Senior Backend Engineer (Python)"}
    assert choose_resume(conn, job) == back
    assert choose_resume(conn, {"title": "Pastry Chef"}) == front
    pin_resume(conn, front)
    pin_resume(conn, back)
    assert {r["id"]: r["pinned"] for r in list_resumes(conn)} == {front: False, back: True}
    assert choose_resume(conn, {"title": "Pastry Chef"}) == back
    unpin_resume(conn)
    assert not any(r["pinned"] for r in list_resumes(conn))
    with pytest.raises(ResumeError) as exc:
        pin_resume(conn, 9999)
    assert str(exc.value) == "No resume with id 9999."


def test_get_resume_text_behaviour(conn, tmp_path):
    from hireember.resumes import ResumeError, add_resume, get_resume_text

    t = add_resume(conn, text_file(tmp_path, "TXT BODY"), "T")
    assert get_resume_text(conn, t) == "TXT BODY"
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(blank_pdf_bytes())
    bare = add_resume(conn, pdf, "Scan")
    with pytest.raises(ResumeError) as exc:
        get_resume_text(conn, bare)
    assert str(exc.value) == "base resume has no text version"
    pdf2 = tmp_path / "cv2.pdf"
    pdf2.write_bytes(blank_pdf_bytes())
    with_text = add_resume(conn, pdf2, "WithText", text_file=text_file(tmp_path, "PDF TEXT"))
    assert get_resume_text(conn, with_text) == "PDF TEXT"


JOB = {"title": "Python Backend Engineer", "site": "Acme", "location": "Berlin",
       "full_description": "Build Python APIs with FastAPI and SQL."}


def _job_text():
    return (f"TITLE: {JOB['title']}\nCOMPANY: {JOB['site']}\nLOCATION: {JOB['location']}\n\n"
            f"DESCRIPTION:\n{JOB['full_description']}")


def _capture(monkeypatch, module, reply):
    seen = []

    class Client:
        def chat(self, messages, max_tokens=None, temperature=None):
            seen.append(messages)
            return reply

    monkeypatch.setattr(f"hireember.scoring.{module}.get_client", lambda *a, **k: Client())
    return seen


def test_score_message_unchanged(monkeypatch):
    from hireember.scoring import scorer

    seen = _capture(monkeypatch, "scorer", "SCORE: 7\nKEYWORDS: a\nREASONING: ok")
    scorer.score_job("BASE TEXT", JOB, None)
    assert seen[0][1]["content"] == f"RESUME:\nBASE TEXT\n\n---\n\nJOB POSTING:\n{_job_text()}"


def test_tailor_message_unchanged(monkeypatch):
    from hireember.scoring import tailor

    from p2_helpers import tailor_json

    seen = _capture(monkeypatch, "tailor", json.dumps(tailor_json()))
    tailor.tailor_resume("BASE TEXT", JOB, profile(), max_retries=0, validation_mode="lenient")
    assert seen[0][1]["content"] == (
        f"ORIGINAL RESUME:\nBASE TEXT\n\n---\n\nTARGET JOB:\n{_job_text()}\n\nReturn the JSON:")


def test_apply_prompt_has_no_excerpt_block_by_default(tmp_path, monkeypatch):
    import hireember.config as config
    from hireember.apply.prompt import build_prompt

    path = tmp_path / "profile.json"
    path.write_text((REPO_ROOT / "profile.example.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    monkeypatch.setattr(config, "APPLY_WORKER_DIR", tmp_path / "workers")
    resume = tmp_path / "r.txt"
    resume.write_text("x")
    resume.with_suffix(".pdf").write_bytes(b"%PDF-1.4")
    job = {"url": "https://j/1", "title": "Eng", "site": "Acme", "tailored_resume_path": str(resume)}
    out = build_prompt(job, "TAILORED BODY")
    assert "RESUME EXCERPTS" not in out
    assert "TAILORED BODY\n\n== COVER LETTER TEXT" in out


def test_resume_row_without_chunks_leaves_prompts_unchanged(conn, monkeypatch):
    from hireember.gating import process_job

    stem = f"legacy_{uuid.uuid4().hex[:6]}"
    base_dir().mkdir(parents=True, exist_ok=True)
    path = base_dir() / f"{stem}.txt"
    path.write_text("Experience\nBuilt Python APIs with FastAPI at Acme.", encoding="utf-8")
    conn.execute("INSERT INTO resumes (name, tags, file_path, pinned, added_at) VALUES (?, '', ?, 0, 'now')",
                 ("Legacy", str(path)))
    conn.commit()
    fake = install_fake_llm(monkeypatch, score=8)
    res = process_job(conn, store_job(conn, "https://j.example/legacy"), profile=profile(),
                      validation_mode="lenient")
    assert res.status == "pending"
    assert "RELEVANT RESUME EXCERPTS" not in fake.texts("scorer")
    assert "RELEVANT RESUME EXCERPTS" not in fake.texts("tailor")
    assert fake.calls["scorer"][0][1]["content"].startswith("RESUME:\nExperience\nBuilt Python APIs")
