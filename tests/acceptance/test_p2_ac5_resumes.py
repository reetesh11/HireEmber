"""Phase 2 AC-5: base resumes (add, list, pin) and resume choice recorded on the ticket."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from hireember.database import close_connection, init_db

from p2_helpers import install_fake_llm, make_resume, profile, store_job, widen_cli_console


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    from hireember import config
    config.ensure_dirs()
    yield c
    close_connection(db)


def test_add_two_resumes_and_list(conn, tmp_path):
    from hireember import config
    from hireember.resumes import list_resumes

    a = make_resume(conn, tmp_path, "Backend", "backend,python", "BACKEND TEXT")
    b = make_resume(conn, tmp_path, "Frontend", "frontend,react", "FRONTEND TEXT")
    rows = list_resumes(conn)
    assert [r["id"] for r in rows] == [a, b]
    assert [r["name"] for r in rows] == ["Backend", "Frontend"]
    assert [r["tags"] for r in rows] == [["backend", "python"], ["frontend", "react"]]
    assert [r["pinned"] for r in rows] == [False, False]
    for r in rows:
        p = Path(r["file_path"])
        assert p.exists() and p.parent.resolve() == (config.APP_DIR / "base_resumes").resolve()
        assert r["added_at"]
    assert Path(rows[0]["file_path"]).read_text(encoding="utf-8") == "BACKEND TEXT"


def test_add_errors(conn, tmp_path):
    from hireember.resumes import ResumeError, add_resume

    make_resume(conn, tmp_path, "Backend", "backend", "x")
    with pytest.raises(ResumeError) as exc:
        add_resume(conn, tmp_path / "missing.txt", "Other")
    assert str(exc.value) == f"File not found: {tmp_path / 'missing.txt'}."
    doc = tmp_path / "cv.docx"
    doc.write_text("x")
    with pytest.raises(ResumeError) as exc:
        add_resume(conn, doc, "Doc")
    assert str(exc.value) == "Unsupported format. Provide a .txt or .pdf file."
    txt = tmp_path / "again.txt"
    txt.write_text("y")
    with pytest.raises(ResumeError) as exc:
        add_resume(conn, txt, "BACKEND")
    assert str(exc.value) == 'A resume named "BACKEND" already exists.'


def test_pin_replaces_and_unpin_clears(conn, tmp_path):
    from hireember.resumes import ResumeError, list_resumes, pin_resume, unpin_resume

    a = make_resume(conn, tmp_path, "A", "x", "a")
    b = make_resume(conn, tmp_path, "B", "y", "b")
    pin_resume(conn, a)
    pin_resume(conn, b)
    assert {r["id"]: r["pinned"] for r in list_resumes(conn)} == {a: False, b: True}
    with pytest.raises(ResumeError) as exc:
        pin_resume(conn, 99)
    assert str(exc.value) == "No resume with id 99."
    assert {r["id"]: r["pinned"] for r in list_resumes(conn)} == {a: False, b: True}
    unpin_resume(conn)
    assert not any(r["pinned"] for r in list_resumes(conn))


def test_resume_text_txt_pdf_and_missing(conn, tmp_path):
    from hireember.resumes import ResumeError, add_resume, get_resume_text

    t = make_resume(conn, tmp_path, "T", "x", "TXT BODY")
    assert get_resume_text(conn, t) == "TXT BODY"
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    bare = add_resume(conn, pdf, "Bare")
    with pytest.raises(ResumeError) as exc:
        get_resume_text(conn, bare)
    assert str(exc.value) == "base resume has no text version"
    side = tmp_path / "cv_text.txt"
    side.write_text("PDF TEXT")
    pdf2 = tmp_path / "cv2.pdf"
    pdf2.write_bytes(b"%PDF-1.4\n%%EOF\n")
    with_text = add_resume(conn, pdf2, "WithText", text_file=side)
    assert get_resume_text(conn, with_text) == "PDF TEXT"


def test_choose_resume_pinned_best_fit_ties_and_none(conn, tmp_path):
    from hireember.resumes import choose_resume, pin_resume

    job = {"title": "Senior Backend Engineer (Python)"}
    assert choose_resume(conn, job) is None
    front = make_resume(conn, tmp_path, "Front", "frontend,react", "f")
    back = make_resume(conn, tmp_path, "Back", "backend,python", "b")
    assert choose_resume(conn, job) == back
    assert choose_resume(conn, {"title": "Pastry Chef"}) == front  # no overlap: lowest id
    tie = make_resume(conn, tmp_path, "Tie", "backend", "t")
    assert choose_resume(conn, {"title": "Backend Developer"}) == back  # tie: lowest id among best
    assert tie > back
    pin_resume(conn, front)
    assert choose_resume(conn, job) == front


def test_update_resume_replaces_stored_text(conn, tmp_path):
    from hireember.resumes import get_resume_text, update_resume

    a = make_resume(conn, tmp_path, "A", "x", "OLD")
    new = tmp_path / "new.txt"
    new.write_text("NEW")
    update_resume(conn, a, new)
    assert get_resume_text(conn, a) == "NEW"


def test_ticket_resume_id_set_for_pinned_and_best_fit(conn, tmp_path, monkeypatch):
    from hireember.gating import score_job_for_ticket
    from hireember.resumes import list_resumes, pin_resume, unpin_resume
    from hireember.tickets import get_ticket

    fake = install_fake_llm(monkeypatch)
    front = make_resume(conn, tmp_path, "Front", "frontend,react", "MARKER-FRONT-RESUME")
    back = make_resume(conn, tmp_path, "Back", "backend,python", "MARKER-BACK-RESUME")
    shown_ids = {r["id"] for r in list_resumes(conn)}

    pin_resume(conn, front)
    r1 = score_job_for_ticket(conn, store_job(conn, "https://j.example/pinned"), profile=profile())
    assert r1.resume_id == front and r1.resume_id in shown_ids
    assert get_ticket(conn, r1.ticket_id)["resume_id"] == front
    assert "MARKER-FRONT-RESUME" in fake.texts("scorer")

    unpin_resume(conn)
    r2 = score_job_for_ticket(conn, store_job(conn, "https://j.example/best"), profile=profile())
    assert r2.resume_id == back
    assert get_ticket(conn, r2.ticket_id)["resume_id"] == back
    assert "MARKER-BACK-RESUME" in fake.texts("scorer")


def test_cli_resume_commands(conn, tmp_path, isolated_db, monkeypatch):
    from hireember.cli import app

    widen_cli_console(monkeypatch)
    runner = CliRunner()
    empty = runner.invoke(app, ["resume", "list"])
    assert empty.exit_code == 0 and 'No base resumes. Add one with "hireember resume add".' in empty.output

    f = tmp_path / "cv.txt"
    f.write_text("cv body")
    added = runner.invoke(app, ["resume", "add", str(f), "--name", "Backend", "--tags", "backend,python"])
    assert added.exit_code == 0, added.output
    assert "Added resume 1: Backend." in added.output
    dup = runner.invoke(app, ["resume", "add", str(f), "--name", "backend"])
    assert dup.exit_code == 1 and 'A resume named "backend" already exists.' in dup.output
    missing = runner.invoke(app, ["resume", "add", str(tmp_path / "no.txt"), "--name", "N"])
    assert missing.exit_code == 1 and "File not found:" in missing.output

    listed = runner.invoke(app, ["resume", "list"])
    assert listed.exit_code == 0, listed.output
    for word in ("Id", "Name", "Tags", "Pinned", "File", "Added", "Backend", "backend"):
        assert word in listed.output

    pinned = runner.invoke(app, ["resume", "pin", "1"])
    assert pinned.exit_code == 0 and "Pinned resume 1." in pinned.output
    bad = runner.invoke(app, ["resume", "pin", "42"])
    assert bad.exit_code == 1 and "No resume with id 42." in bad.output
    un = runner.invoke(app, ["resume", "unpin"])
    assert un.exit_code == 0 and "Unpinned." in un.output
