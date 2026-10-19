"""Phase 0d init step 1: one resume file, PDF extraction, confirmation, registration (AC-2..5, 10, 11)."""

import pytest

from p0d_helpers import (
    BODY, DISTINCT_WORDS, FULL_LINES, Q_CONFIRM, Q_OVERWRITE, Q_PATH, Q_TXT, Script,
    console, isolate, output, write_pdf,
)

TXT_A = "Alpha resume text\n" + "\n".join(BODY) + "\n"


@pytest.fixture
def env(monkeypatch, tmp_path):
    return isolate(monkeypatch, tmp_path)


def run(conn, ask):
    from hireember.wizard.init import run_resume_step

    c = console()
    run_resume_step(conn, ask, console=c)
    return output(c)


def test_text_pdf_leaves_pdf_and_extracted_text_without_text_prompt(env):
    conn, data, src = env
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    ask = Script({Q_PATH: [str(pdf)], Q_CONFIRM: ["y"]})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_CONFIRM]
    assert (data / "resume.pdf").read_bytes() == pdf.read_bytes()
    text = (data / "resume.txt").read_text(encoding="utf-8")
    assert text.strip()
    for word in DISTINCT_WORDS:
        assert word in text


def test_txt_resume_is_copied_and_nothing_else_is_asked(env):
    conn, data, src = env
    txt = src / "me.txt"
    txt.write_bytes(TXT_A.encode("utf-8"))
    ask = Script({Q_PATH: [str(txt)], Q_CONFIRM: [""]})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_CONFIRM]
    assert (data / "resume.txt").read_bytes() == txt.read_bytes()
    assert not (data / "resume.pdf").exists()


def test_quoted_path_and_validation_messages(env):
    conn, data, src = env
    (src / "notes.docx").write_text("x")
    txt = src / "me.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(src / "nope.txt"), str(src / "notes.docx"), f'  "{txt}"  '],
                  Q_CONFIRM: ["y"]})
    out = run(conn, ask)
    assert "File not found:" in out and "nope.txt" in out
    assert "Unsupported format. Provide a .txt or .pdf file." in out
    assert ask.log == [Q_PATH, Q_PATH, Q_PATH, Q_CONFIRM]
    assert (data / "resume.txt").read_text(encoding="utf-8") == TXT_A


@pytest.mark.parametrize("kind", ["image-only", "blank-page", "zero-bytes", "corrupt", "short-text"])
def test_pdf_without_usable_text_asks_for_txt_and_finishes(env, kind):
    conn, data, src = env
    bad = src / "bad.pdf"
    if kind == "image-only":
        write_pdf(bad, None, rect_only=True)
    elif kind == "blank-page":
        write_pdf(bad, None)
    elif kind == "zero-bytes":
        bad.write_bytes(b"")
    elif kind == "corrupt":
        bad.write_bytes(b"definitely not a pdf \x00\x01")
    else:
        write_pdf(bad, ["Jane Doe", "Too short to be a resume."])
    txt = src / "fallback.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(bad)], Q_TXT: [str(txt)], Q_CONFIRM: ["y"]})
    out = run(conn, ask)
    assert ask.log == [Q_PATH, Q_TXT, Q_CONFIRM]
    assert ("Could not read any text from bad.pdf. It may be a scanned image, password-protected, "
            "or damaged. Please give a plain-text (.txt) version of your resume instead.") in out
    assert "Traceback" not in out
    assert not (data / "resume.pdf").exists()
    assert (data / "resume.txt").read_text(encoding="utf-8") == TXT_A
    from hireember.resumes import list_resumes

    assert len(list_resumes(conn)) == 1


def test_txt_prompt_rejects_non_txt_and_missing(env):
    conn, data, src = env
    bad = src / "bad.pdf"
    bad.write_bytes(b"")
    other = src / "other.pdf"
    other.write_bytes(b"")
    txt = src / "fallback.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(bad)], Q_TXT: [str(other), str(src / "gone.txt"), str(txt)],
                  Q_CONFIRM: ["y"]})
    out = run(conn, ask)
    assert "Please provide a .txt file." in out
    assert "File not found:" in out and "gone.txt" in out
    assert ask.log == [Q_PATH, Q_TXT, Q_TXT, Q_TXT, Q_CONFIRM]
    assert (data / "resume.txt").read_text(encoding="utf-8") == TXT_A


def test_confirmation_output_shows_lines_count_and_path(env):
    conn, data, src = env
    lines = [f"Line number {i} " + "x" * 120 for i in range(1, 16)]
    lines.insert(2, "")
    txt = src / "me.txt"
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    seen = {}

    def snapshot():
        seen["out"] = output(c)

    from hireember.wizard.init import run_resume_step

    c = console()
    ask = Script({Q_PATH: [str(txt)], Q_CONFIRM: ["y"]}, hooks={Q_CONFIRM: snapshot})
    run_resume_step(conn, ask, console=c)
    shown = seen["out"]  # everything printed before the confirmation prompt
    total = len((data / "resume.txt").read_text(encoding="utf-8"))
    assert f"Characters read: {total}" in shown
    assert f"Saved as {data / 'resume.txt'} (you can edit this file)." in shown
    assert "Line number 10 " in shown
    assert "Line number 11 " not in shown
    assert "Line number 1 " + "x" * 86 in shown  # truncated to 100 characters
    assert "x" * 87 not in shown


def test_pdf_character_count_matches_saved_text(env):
    conn, data, src = env
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    out = run(conn, Script({Q_PATH: [str(pdf)], Q_CONFIRM: ["y"]}))
    assert f"Characters read: {len((data / 'resume.txt').read_text(encoding='utf-8'))}" in out


def test_declining_confirmation_reasks_and_registers_only_when_confirmed(env):
    from hireember.resumes import list_resumes

    conn, data, src = env
    first = write_pdf(src / "first.pdf", ["First candidate"] + BODY)
    second = write_pdf(src / "second.pdf", ["Second candidate"] + [b.replace("backend", "frontend") for b in BODY])
    counts = []
    ask = Script({Q_PATH: [str(first), str(second)], Q_CONFIRM: ["n", "y"]},
                 hooks={Q_CONFIRM: lambda: counts.append(len(list_resumes(conn)))})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_CONFIRM, Q_PATH, Q_CONFIRM]
    assert counts == [0, 0]
    assert len(list_resumes(conn)) == 1
    text = (data / "resume.txt").read_text(encoding="utf-8")
    assert "Second candidate" in text and "First candidate" not in text


def test_keyboard_interrupt_propagates(env):
    conn, data, src = env

    def ask(question, **kwargs):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(conn, ask)


# -- registration (AC-5) --------------------------------------------------------------------


def test_pdf_run_registers_master_resume_with_text(env):
    from hireember.resumes import get_resume_text, list_resumes

    conn, data, src = env
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    run(conn, Script({Q_PATH: [str(pdf)], Q_CONFIRM: ["y"]}))
    rows = list_resumes(conn)
    assert [r["name"] for r in rows] == ["Master resume"]
    assert rows[0]["file_path"].lower().endswith(".pdf")
    assert "observability" in get_resume_text(conn, rows[0]["id"])


def test_txt_run_registers_master_resume(env):
    from hireember.resumes import get_resume_text, list_resumes

    conn, data, src = env
    txt = src / "me.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    run(conn, Script({Q_PATH: [str(txt)], Q_CONFIRM: ["y"]}))
    rows = list_resumes(conn)
    assert [r["name"] for r in rows] == ["Master resume"]
    assert get_resume_text(conn, rows[0]["id"]) == TXT_A


def test_running_pdf_step_twice_leaves_one_entry_and_no_error(env):
    from hireember.resumes import list_resumes

    conn, data, src = env
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    ask = Script({Q_PATH: [str(pdf)], Q_CONFIRM: ["y"]})
    run(conn, ask)
    out = run(conn, ask)
    assert len(list_resumes(conn)) == 1
    assert Q_OVERWRITE not in ask.log  # resume.txt came from extraction: replaced silently
    assert "already exists." not in out and "Traceback" not in out


def test_running_txt_step_twice_leaves_one_entry_and_no_error(env):
    from hireember.resumes import list_resumes

    conn, data, src = env
    txt = src / "me.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(txt)], Q_OVERWRITE: ["y"], Q_CONFIRM: ["y"]})
    run(conn, ask)
    out = run(conn, ask)
    assert len(list_resumes(conn)) == 1
    assert "A resume named" not in out and "Traceback" not in out


def test_resume_list_command_shows_one_row_after_two_runs(env, monkeypatch):
    from typer.testing import CliRunner

    from hireember import database
    from hireember.cli import app

    conn, data, src = env
    monkeypatch.setattr(database, "get_connection", lambda *a, **k: conn)
    txt = src / "me.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(txt)], Q_OVERWRITE: ["y"], Q_CONFIRM: ["y"]})
    run(conn, ask)
    run(conn, ask)
    result = CliRunner().invoke(app, ["resume", "list"])
    assert result.exit_code == 0, result.output
    assert result.output.count("Master resume") == 1


# -- overwrite guard (AC-10) ------------------------------------------------------------------


@pytest.mark.parametrize("reply", ["n", "", "N", "maybe"])
def test_declined_overwrite_keeps_user_resume_txt_byte_for_byte(env, reply):
    conn, data, src = env
    original = b"MY HAND WRITTEN RESUME\r\nkeep me \xe2\x9c\x93\n"
    (data / "resume.txt").write_bytes(original)
    new = src / "new.txt"
    new.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(new)], Q_OVERWRITE: [reply], Q_CONFIRM: ["y"]})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_OVERWRITE, Q_CONFIRM]
    assert (data / "resume.txt").read_bytes() == original


@pytest.mark.parametrize("reply", ["y", "YES", "Yes"])
def test_accepted_overwrite_replaces_resume_txt(env, reply):
    conn, data, src = env
    (data / "resume.txt").write_text("old user text", encoding="utf-8")
    new = src / "new.txt"
    new.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(new)], Q_OVERWRITE: [reply], Q_CONFIRM: ["y"]})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_OVERWRITE, Q_CONFIRM]
    assert (data / "resume.txt").read_text(encoding="utf-8") == TXT_A


def test_declined_overwrite_with_pdf_still_copies_pdf_but_keeps_txt(env):
    conn, data, src = env
    (data / "resume.txt").write_text("old user text\n", encoding="utf-8")
    pdf = write_pdf(src / "me.pdf", FULL_LINES)
    ask = Script({Q_PATH: [str(pdf)], Q_OVERWRITE: ["n"], Q_CONFIRM: ["y"]})
    run(conn, ask)
    assert ask.log == [Q_PATH, Q_OVERWRITE, Q_CONFIRM]
    assert (data / "resume.txt").read_text(encoding="utf-8") == "old user text\n"
    assert (data / "resume.pdf").read_bytes() == pdf.read_bytes()


def test_no_overwrite_prompt_when_no_resume_txt_exists(env):
    conn, data, src = env
    txt = src / "me.txt"
    txt.write_text(TXT_A, encoding="utf-8")
    ask = Script({Q_PATH: [str(txt)], Q_CONFIRM: ["y"]})
    run(conn, ask)
    assert Q_OVERWRITE not in ask.log

