"""Phase 2 AC-9: editing a base resume never changes a submitted ticket's files."""

from pathlib import Path

import pytest

from hireember.database import close_connection, init_db

from p2_helpers import install_fake_llm, make_resume, profile, store_job


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    from hireember import config
    config.ensure_dirs()
    yield c
    close_connection(db)


def test_submitted_ticket_keeps_files_after_resume_edit(conn, tmp_path, monkeypatch):
    from hireember.gating import process_job
    from hireember.resumes import update_resume
    from hireember.tickets import get_ticket, set_status

    install_fake_llm(monkeypatch, score=9)
    rid = make_resume(conn, tmp_path, "Backend", "backend", "OLD BASE TEXT")
    first = process_job(conn, store_job(conn, "https://j.example/one"), profile=profile(),
                        validation_mode="lenient")
    tid = first.ticket_id
    set_status(conn, tid, "applied", reason="submitted")
    before = get_ticket(conn, tid)
    r_bytes = Path(before["tailored_resume_path"]).read_bytes()
    c_bytes = Path(before["cover_letter_path"]).read_bytes()

    new = tmp_path / "new.txt"
    new.write_text("NEW BASE TEXT", encoding="utf-8")
    update_resume(conn, rid, new)
    second = process_job(conn, store_job(conn, "https://j.example/two"), profile=profile(),
                         validation_mode="lenient")

    after = get_ticket(conn, tid)
    for k in ("tailored_resume_path", "cover_letter_path", "resume_id"):
        assert after[k] == before[k]
    assert Path(after["tailored_resume_path"]).read_bytes() == r_bytes
    assert Path(after["cover_letter_path"]).read_bytes() == c_bytes
    assert second.tailored_resume_path != before["tailored_resume_path"]
    assert second.cover_letter_path != before["cover_letter_path"]
