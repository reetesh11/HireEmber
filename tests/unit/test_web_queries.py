"""Dashboard queries (implementation tests)."""

import csv
import io

import pytest

from hireember.database import close_connection, init_db
from hireember.web import queries


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    for i, status in enumerate(("pending", "applied")):
        c.execute("INSERT INTO jobs (url, title, site) VALUES (?, ?, 'Site')",
                  (f"https://j/{i}", f"T{i}"))
        c.execute("INSERT INTO tickets (job_url, status, score, created_at, updated_at) "
                  "VALUES (?, ?, ?, '2026-01-02T00:00:00', '2026-01-03T00:00:00')",
                  (f"https://j/{i}", status, i * 50))
    c.commit()
    yield c
    close_connection(db)


def test_links_and_counts(conn):
    rows = {r["status"]: r for r in queries.list_tickets(conn)}
    assert rows["pending"]["link"]["url"] == "https://j/0"
    assert rows["applied"]["link"] is None
    assert queries.status_counts(list(rows.values()))["applied"] == 1


def test_filter_validation_and_sort(conn):
    with pytest.raises(queries.FilterError):
        queries.list_tickets(conn, queries.TicketFilters(score_min=101))
    with pytest.raises(queries.FilterError):
        queries.list_tickets(conn, queries.TicketFilters(date_from="bad"))
    rows = queries.list_tickets(conn, sort="score", direction="desc")
    assert [r["score"] for r in rows] == [50, 0]
    assert len(queries.list_tickets(conn, queries.TicketFilters(company="site"))) == 2
    assert queries.list_tickets(conn, queries.TicketFilters(company="100%")) == []


def test_csv_roundtrip_and_guard(conn):
    conn.execute("UPDATE tickets SET notes = '=1+1, \"x\"' WHERE job_url = 'https://j/0'")
    conn.commit()
    rows = list(csv.reader(io.StringIO(queries.tickets_csv(conn), newline="")))
    assert rows[0][0] == "company" and len(rows) == 3
    assert any(r[8] == "'=1+1, \"x\"" for r in rows[1:])


def test_next_step_sign_in():
    assert queries.next_step("Sign in required") == "Sign in"
    assert queries.next_step(None) == "Review"
