"""Dashboard runs page: escaping, fragment, empty state."""

import pytest

from hireember.web import queries


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_empty_and_fragment(conn):
    page = queries.runs_html(conn)
    assert "<html" in page and "<h2>Runs</h2>" in page and "No runs yet." in page
    assert "<html" not in queries.runs_html(conn, fragment=True)


def test_values_are_escaped(conn):
    conn.execute('INSERT INTO runs (kind, "trigger", status, started_at) '
                 "VALUES ('full', 'manual', '<b>bad</b>', '2026-01-01')")
    conn.commit()
    html = queries.runs_html(conn)
    assert "<b>bad</b>" not in html and "&lt;b&gt;bad&lt;/b&gt;" in html
