"""Phase 7 AC-4: text copy, sections and bounded chunks written on add, replace and re-extract."""

from pathlib import Path

import pytest

from p7_helpers import RESUME_TEXT, chunk_rows, docx_bytes, text_file


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


# -- split_sections ----------------------------------------------------------

def test_sections_constants():
    from hireember.resume_index import MAX_CHUNK_CHARS, SECTIONS

    assert SECTIONS == ("summary", "experience", "education", "skills", "other")
    assert MAX_CHUNK_CHARS == 800


def test_split_sections_by_headings_case_insensitive():
    from hireember.resume_index import split_sections

    text = ("Professional Summary\nBackend dev.\n\nWORK EXPERIENCE:\nAcme - Python\n\n"
            "education\nBSc\n\nTechnical Skills\nPython, SQL\n")
    out = split_sections(text)
    assert [s for s, _ in out] == ["summary", "experience", "education", "skills"]
    bodies = dict(out)
    assert "Backend dev." in bodies["summary"]
    assert "Acme - Python" in bodies["experience"]
    assert "BSc" in bodies["education"]
    assert "Python, SQL" in bodies["skills"]
    assert "Professional Summary" not in bodies["summary"]


def test_text_before_first_heading_short_goes_to_summary():
    from hireember.resume_index import split_sections

    out = split_sections("Jane Doe, backend engineer\n\nExperience\nAcme\n")
    assert [s for s, _ in out] == ["summary", "experience"]
    assert "Jane Doe" in out[0][1]


def test_text_before_first_heading_long_goes_to_other():
    from hireember.resume_index import split_sections

    out = split_sections(("word " * 200) + "\n\nSkills\nPython\n")
    assert [s for s, _ in out] == ["other", "skills"]


def test_no_headings_is_one_other_section():
    from hireember.resume_index import split_sections

    out = split_sections("Just a paragraph of text about Python.\nAnd another line.")
    assert len(out) == 1 and out[0][0] == "other"
    assert "Python" in out[0][1]


def test_empty_sections_are_dropped():
    from hireember.resume_index import split_sections

    out = split_sections("Experience\n\nEducation\nBSc\n")
    assert [s for s, _ in out] == ["education"]


# -- chunk_text --------------------------------------------------------------

def test_chunks_are_bounded_and_nonempty():
    from hireember.resume_index import chunk_text

    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(20))
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(c.strip() and len(c) <= 800 for c in chunks)
    joined = " ".join(chunks)
    for i in range(20):
        assert f"Paragraph {i} " in joined


def test_chunks_pack_on_line_boundaries():
    from hireember.resume_index import chunk_text

    lines = [f"line number {i:03d} " + "x" * 40 for i in range(60)]
    chunks = chunk_text("\n".join(lines))
    for c in chunks:
        for part in c.split("\n"):
            assert part in lines


def test_overlong_line_is_split_on_whitespace():
    from hireember.resume_index import chunk_text

    chunks = chunk_text("alpha " * 500)
    assert len(chunks) > 1
    assert all(len(c) <= 800 and c.strip() for c in chunks)
    assert all(w == "alpha" for c in chunks for w in c.split())


def test_custom_max_chars_and_blank_text():
    from hireember.resume_index import chunk_text

    assert chunk_text("   \n\n \t ") == []
    assert chunk_text("") == []
    assert all(len(c) <= 50 for c in chunk_text("one two three four five six seven eight nine ten " * 5, 50))


# -- replace_chunks / count / delete ----------------------------------------

def test_replace_chunks_positions_and_replacement(conn, tmp_path):
    from hireember.resume_index import count_chunks, delete_chunks, replace_chunks
    from hireember.resumes import add_resume

    rid = add_resume(conn, text_file(tmp_path, "x"), "Idx")
    n = replace_chunks(conn, rid, RESUME_TEXT)
    assert n >= 4 and count_chunks(conn, rid) == n
    rows = chunk_rows(conn, rid)
    assert [p for _, p in rows] == list(range(n))
    assert {s for s, _ in rows} <= {"summary", "experience", "education", "skills", "other"}
    assert {"experience", "education", "skills"} <= {s for s, _ in rows}
    n2 = replace_chunks(conn, rid, "Skills\nOnly Rust")
    assert n2 == 1 and count_chunks(conn, rid) == 1
    assert chunk_rows(conn, rid) == [("skills", 0)]
    delete_chunks(conn, rid)
    assert count_chunks(conn, rid) == 0


# -- extraction on add / replace / re-extract --------------------------------

def test_add_txt_writes_chunks_and_text_is_readable(conn, tmp_path):
    from hireember.resumes import add_resume, get_resume_text, list_resumes

    rid = add_resume(conn, text_file(tmp_path), "Txt one")
    assert get_resume_text(conn, rid) == RESUME_TEXT
    row = [r for r in list_resumes(conn) if r["id"] == rid][0]
    assert row["extract_status"] == "extracted" and row["chunk_count"] == len(chunk_rows(conn, rid)) >= 4


def test_add_docx_writes_text_copy_next_to_file(conn, tmp_path):
    from hireember.resumes import add_resume, get_resume_text, list_resumes

    src = tmp_path / "cv.docx"
    src.write_bytes(docx_bytes(["Experience", "Built Python services at Acme.", "Skills", "Python"]))
    rid = add_resume(conn, src, "Docx one")
    stored = Path([r for r in list_resumes(conn) if r["id"] == rid][0]["file_path"])
    assert stored.suffix == ".docx"
    copy = stored.with_name(stored.name + ".txt")
    assert copy.is_file()
    assert "Built Python services at Acme." in get_resume_text(conn, rid)
    assert {s for s, _ in chunk_rows(conn, rid)} == {"experience", "skills"}


def test_pdf_with_text_copy_is_chunked(conn, tmp_path):
    from hireember.resumes import add_resume, list_resumes

    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    rid = add_resume(conn, pdf, "Pdf text", text_file=text_file(tmp_path))
    row = [r for r in list_resumes(conn) if r["id"] == rid][0]
    assert row["extract_status"] == "extracted" and row["chunk_count"] >= 4


def test_reextract_replaces_old_chunks_entirely(conn, tmp_path):
    from hireember.resume_index import count_chunks, replace_chunks
    from hireember.resumes import add_resume, extract_resume, search

    rid = add_resume(conn, text_file(tmp_path), "Re one")
    expected = count_chunks(conn, rid)
    replace_chunks(conn, rid, "Skills\nstalemarker content")
    assert search(conn, "stalemarker")
    result = extract_resume(conn, rid)
    assert (result.status, result.chunks) == ("extracted", expected)
    assert count_chunks(conn, rid) == expected
    assert search(conn, "stalemarker") == []


def test_replacing_file_replaces_chunks(conn, tmp_path):
    from hireember.resumes import add_resume, get_resume_text, search, update_resume

    rid = add_resume(conn, text_file(tmp_path, "Skills\nCobol mainframe"), "Rep one")
    assert search(conn, "Cobol")
    update_resume(conn, rid, text_file(tmp_path, "Skills\nHaskell functional"))
    assert search(conn, "Cobol") == []
    assert [h["resume_id"] for h in search(conn, "Haskell")] == [rid]
    assert "Haskell" in get_resume_text(conn, rid)
