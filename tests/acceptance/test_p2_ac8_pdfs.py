"""Phase 2 AC-8: a passing role's ticket holds tailored resume and cover letter PDFs."""

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
    make_resume(c, tmp_path, "Backend", "backend", "BASE RESUME TEXT")
    yield c
    close_connection(db)


def _assert_pdf(path):
    data = Path(path).read_bytes()
    assert data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    assert len(data) > 20


def test_passing_role_has_two_valid_pdfs(conn, monkeypatch):
    from hireember import config
    from hireember.gating import process_job
    from hireember.tickets import get_ticket

    fake = install_fake_llm(monkeypatch, score=8)
    res = process_job(conn, store_job(conn, "https://j.example/ok"), profile=profile(),
                      validation_mode="lenient")
    assert res.status == "pending"
    t = get_ticket(conn, res.ticket_id)
    assert t["tailored_resume_path"] and t["cover_letter_path"]
    assert (res.tailored_resume_path, res.cover_letter_path) == (t["tailored_resume_path"], t["cover_letter_path"])
    for p in (t["tailored_resume_path"], t["cover_letter_path"]):
        assert p.endswith(".pdf")
        _assert_pdf(p)
    assert Path(t["tailored_resume_path"]).parent.resolve() == config.TAILORED_DIR.resolve()
    assert Path(t["cover_letter_path"]).parent.resolve() == config.COVER_LETTER_DIR.resolve()
    assert f"ticket{res.ticket_id}_" in Path(t["tailored_resume_path"]).name
    assert len(fake.calls["tailor"]) == 1 and len(fake.calls["cover_letter"]) == 1


def test_write_text_pdf(tmp_path):
    from hireember.scoring.pdf import write_text_pdf

    out = write_text_pdf("Hello\nWorld", tmp_path / "x.pdf")
    assert Path(out) == tmp_path / "x.pdf"
    _assert_pdf(out)
