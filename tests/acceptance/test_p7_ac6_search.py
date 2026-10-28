"""Phase 7 AC-6: resumes.search ranks chunks and never raises."""

import pytest

from p7_helpers import text_file


@pytest.fixture
def conn(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


@pytest.fixture
def two(conn, tmp_path):
    from hireember.resumes import add_resume

    a = add_resume(conn, text_file(
        tmp_path, "Experience\nWrote Python services and tools for payments.\n\nSkills\nGardening, Cooking"),
        "Alpha")
    b = add_resume(conn, text_file(
        tmp_path, "Experience\nManaged a warehouse team.\n\nSkills\nForklift, Python scripting"), "Beta")
    return a, b


def test_result_shape(conn, two):
    from hireember.resumes import search

    hits = search(conn, "payments")
    assert len(hits) == 1
    h = hits[0]
    for key in ("chunk_id", "resume_id", "resume_name", "section", "position", "text", "score"):
        assert key in h
    assert h["resume_id"] == two[0] and h["resume_name"] == "Alpha"
    assert h["section"] == "experience" and "payments" in h["text"]
    assert isinstance(h["position"], int) and isinstance(h["score"], float)


def test_python_experience_ranks_python_chunk_first(conn, two):
    from hireember.resumes import search

    hits = search(conn, "Python experience")
    assert hits
    assert "Python" in hits[0]["text"]
    texts = [h["text"] for h in hits]
    no_python = [i for i, t in enumerate(texts) if "Python" not in t]
    with_python = [i for i, t in enumerate(texts) if "Python" in t]
    assert not no_python or max(with_python) < min(no_python)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_scoped_to_one_resume(conn, two):
    from hireember.resumes import search

    hits = search(conn, "Python", resume_id=two[1])
    assert hits and {h["resume_id"] for h in hits} == {two[1]}
    assert {h["resume_id"] for h in search(conn, "Python")} == set(two)


def test_limit_caps_results(conn, two):
    from hireember.resumes import search

    assert len(search(conn, "Python", limit=1)) == 1
    assert len(search(conn, "Python Experience Skills", limit=2)) <= 2
    assert search(conn, "Python", limit=0) == []


@pytest.mark.parametrize("query", ["", "   ", "\n\t", "!!! ??? ...", "---", '""', "*", ":"])
def test_blank_or_unusable_query_returns_empty(conn, two, query):
    from hireember.resumes import search

    assert search(conn, query) == []


def test_empty_store_returns_empty(conn):
    from hireember.resumes import search

    assert search(conn, "Python") == []


def test_unknown_resume_id_returns_empty(conn, two):
    from hireember.resumes import search

    assert search(conn, "Python", resume_id=9999) == []


@pytest.mark.parametrize("query", [
    'Python "unterminated', "Py*", "-Python", "foo:bar", "(Python", "Python)", "a^b", "Python AND",
    "OR Python", "NEAR(Python", "Python OR", "AND", "NOT", "c++ \"", "'; DROP TABLE resumes; --"])
def test_fts_special_characters_never_raise(conn, two, query):
    from hireember.resumes import search

    assert isinstance(search(conn, query), list)


def test_terms_are_or_matched(conn, two):
    from hireember.resumes import search

    hits = search(conn, "payments warehouse")
    assert {h["resume_id"] for h in hits} == set(two)


def test_search_chunks_matches_search(conn, two):
    from hireember.resume_index import search_chunks
    from hireember.resumes import search

    assert [h["chunk_id"] for h in search_chunks(conn, "Python")] == [h["chunk_id"] for h in search(conn, "Python")]
