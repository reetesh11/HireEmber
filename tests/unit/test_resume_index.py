"""Resume chunk store and keyword search (implementation tests)."""

import pytest

from hireember.database import close_connection, init_db
from hireember.resume_index import (chunk_text, count_chunks, delete_chunks, replace_chunks, search_chunks,
                                    split_sections)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    yield c
    close_connection(db)


def test_headings_and_pre_heading_rule():
    text = "Jane Doe\n\nPROFESSIONAL SUMMARY:\nHello\nWork Experience\nAcme\nSkills\nPython\nEducation\n"
    assert split_sections(text) == [("summary", "Jane Doe"), ("summary", "Hello"), ("experience", "Acme"),
                                    ("skills", "Python")]
    assert split_sections("just text\nmore") == [("other", "just text\nmore")]
    long_pre = "x " * 400
    assert split_sections(long_pre + "\nSkills\nA")[0][0] == "other"
    assert split_sections("") == []


def test_chunk_bounds():
    assert chunk_text("  \n ") == []
    chunks = chunk_text("word " * 500, 100)
    assert chunks and all(0 < len(c) <= 100 for c in chunks)
    assert chunk_text("a\nb\nc", 800) == ["a\nb\nc"]


def test_replace_search_and_delete(conn):
    n = replace_chunks(conn, 1, "Skills\nPython experience\nExperience\nJava work")
    assert n == 2 and count_chunks(conn, 1) == 2
    hits = search_chunks(conn, "Python experience")
    assert hits[0]["text"] == "Python experience" and hits[0]["position"] == 0
    assert search_chunks(conn, "python", resume_id=2) == []
    assert len(search_chunks(conn, "python experience java", limit=1)) == 1
    for q in ('"', "AND OR NEAR", "a*", "-", "()^:", "  ", ""):
        search_chunks(conn, q)
    replace_chunks(conn, 1, "Nothing here")
    assert search_chunks(conn, "python") == []
    delete_chunks(conn, 1)
    assert search_chunks(conn, "nothing") == []
