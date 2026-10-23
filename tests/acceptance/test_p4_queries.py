"""Phase 4: ticket queries - links, blocked queue, filters, CSV, performance (AC-1, 2, 4, 6, 9)."""

import csv
import io
import time

import pytest

from p4_helpers import STATUSES, make_ticket, seed_many


@pytest.fixture
def conn(isolated_db):
    from hireember.database import close_connection, init_db

    c = init_db()
    yield c
    close_connection(isolated_db)


def by_id(rows):
    return {r["id"]: r for r in rows}


# -- AC-1: links ------------------------------------------------------------

def test_status_link_for_each_of_the_seven_statuses(conn):
    from hireember.web.queries import NO_LINK, list_tickets

    assert NO_LINK == "No link available"
    cols = {
        "pending": {},
        "started": {"tailored_resume_path": "/data/t/tailored_resume.txt"},
        "applying": {"session_link": "http://127.0.0.1:9333"},
        "blocked for human": {"status_reason": "captcha"},
        "applied": {"confirmation_link": "https://jobs.example/confirm/1"},
        "skipped": {},
        "closed": {},
    }
    ids = {s: make_ticket(conn, f"link{i}", s, **cols[s]) for i, s in enumerate(STATUSES)}
    conn.execute("INSERT INTO queue_items (ticket_id, kind, reason, page_link) "
                 "VALUES (?, 'captcha', 'captcha', 'https://jobs.example/page/needs-action')",
                 (ids["blocked for human"],))
    conn.commit()
    rows = by_id(list_tickets(conn))
    link = {s: rows[ids[s]]["link"] for s in STATUSES}
    assert link["pending"] == {"label": "Job posting", "url": "https://jobs.example/link0",
                               "local": False}
    assert link["started"] == {"label": "Tailored files", "url": "/data/t/tailored_resume.txt",
                               "local": True}
    assert link["applying"] == {"label": "Live browser session", "url": "http://127.0.0.1:9333",
                                "local": False}
    assert link["blocked for human"] == {"label": "Page needing action",
                                         "url": "https://jobs.example/page/needs-action",
                                         "local": False}
    assert link["applied"] == {"label": "Confirmation", "url": "https://jobs.example/confirm/1",
                               "local": False}
    assert link["skipped"]["label"] == "Job posting"
    assert link["skipped"]["url"] == "https://jobs.example/link5"
    assert link["closed"]["label"] == "Job posting"


def test_status_link_is_none_when_nothing_is_stored(conn):
    from hireember.web.queries import list_tickets

    ids = [make_ticket(conn, f"nolink{i}", s) for i, s in enumerate(
        ("started", "applying", "blocked for human", "applied"))]
    rows = by_id(list_tickets(conn))
    assert all(rows[i]["link"] is None for i in ids)


def test_blocked_link_falls_back_to_resume_link(conn):
    from hireember.web.queries import list_tickets

    tid = make_ticket(conn, "fallback", "blocked for human", resume_link="https://jobs.example/r")
    row = by_id(list_tickets(conn))[tid]
    assert row["link"]["label"] == "Page needing action"
    assert row["link"]["url"] == "https://jobs.example/r"


def test_status_link_pure_function(conn):
    from hireember.web.queries import status_link

    assert status_link({"status": "applied", "confirmation_link": ""}) is None
    got = status_link({"status": "applied", "confirmation_link": "C:\\files\\x.pdf"})
    assert got["local"] is True
    assert status_link({"status": "pending", "job_url": "https://x.example/a"})["local"] is False


def test_list_ticket_dict_has_contract_keys(conn):
    from hireember.web.queries import list_tickets

    make_ticket(conn, "keys", "pending")
    row = list_tickets(conn)[0]
    for key in ("id company title location status status_reason score resume_id resume_name "
                "applied_date created_at updated_at notes referral_note job_url link").split():
        assert key in row, key
    assert row["company"] == "Acme"
    assert row["status"] == "pending"


def test_status_counts_zero_filled(conn):
    from hireember.tickets import ALLOWED_STATUSES
    from hireember.web.queries import list_tickets, status_counts

    make_ticket(conn, "c1", "pending")
    make_ticket(conn, "c2", "pending")
    make_ticket(conn, "c3", "closed")
    counts = status_counts(list_tickets(conn))
    assert set(counts) == set(ALLOWED_STATUSES)
    assert counts["pending"] == 2 and counts["closed"] == 1 and counts["applied"] == 0


# -- AC-2: blocked queue ----------------------------------------------------

def test_next_step_mapping():
    from hireember.web.queries import next_step

    review = "Review and complete this step yourself"
    expected = {
        "account needed": "Create an account", "captcha": "Solve the CAPTCHA",
        "CAPTCHA": "Solve the CAPTCHA", "unknown question": "Answer the question",
        "conflicting answers": "Answer the question", "sensitive question": "Answer the question",
        "identity check": review, "video or biometric": review, "manual site": review,
        "manual ATS": review, "Sign in required": "Sign in", "login failed": "Sign in",
        "review before submit": "Review", "outcome unknown": "Review", "duplicate": "Review",
        "something else": "Review", None: "Review",
    }
    for kind, step in expected.items():
        assert next_step(kind) == step, kind


def test_blocked_queue_counts_and_entries(conn):
    from hireember import answers
    from hireember.web.queries import blocked_queue

    assert blocked_queue(conn) == []
    t1 = make_ticket(conn, "b1", "blocked for human", status_reason="account needed")
    conn.execute("INSERT INTO queue_items (ticket_id, kind, reason, page_link) VALUES "
                 "(?, 'account needed', 'account needed', 'https://jobs.example/signup')", (t1,))
    t2 = make_ticket(conn, "b2", "blocked for human")
    qid = answers.queue_question(conn, t2, "unknown question", "What is your favourite colour?")
    t3 = make_ticket(conn, "b3", "blocked for human", status_reason="")
    make_ticket(conn, "notblocked", "pending")
    conn.commit()

    items = {i["ticket_id"]: i for i in blocked_queue(conn)}
    assert set(items) == {t1, t2, t3}
    assert items[t1]["reason"] == "account needed"
    assert items[t1]["next_step"] == "Create an account"
    assert items[t1]["link"]["url"] == "https://jobs.example/signup"
    assert items[t2]["reason"] == "unknown question"
    assert items[t2]["next_step"] == "Answer the question"
    assert items[t2]["question"] == "What is your favourite colour?"
    assert items[t2]["queue_item_id"] == qid
    assert items[t3]["reason"] == "Needs your attention"
    assert items[t3]["next_step"]
    for item in items.values():
        for key in ("company", "title", "reason", "next_step", "link", "queue_item_id",
                    "question", "kind"):
            assert key in item


def test_blocked_queue_ignores_resolved_items(conn):
    from hireember.web.queries import blocked_queue

    t = make_ticket(conn, "res", "blocked for human", status_reason="manual site")
    conn.execute("INSERT INTO queue_items (ticket_id, kind, reason, resolved_at) "
                 "VALUES (?, 'captcha', 'captcha', '2026-01-01T00:00:00')", (t,))
    conn.commit()
    item = blocked_queue(conn)[0]
    assert item["reason"] == "manual site"
    assert item["queue_item_id"] is None


# -- AC-9: filters ----------------------------------------------------------

def seed_filter_set(conn, tmp_path):
    from hireember import resumes

    rfile = tmp_path / "r.txt"
    rfile.write_text("resume text", encoding="utf-8")
    rid = resumes.add_resume(conn, rfile, "Backend CV")
    a = make_ticket(conn, "fa", company="Acme Corp", score=9, resume_id=rid,
                    created_at="2026-03-10T09:00:00")
    b = make_ticket(conn, "fb", company="Globex", score=5, created_at="2026-03-20T09:00:00")
    c = make_ticket(conn, "fc", company="acme labs", score=7, created_at="2026-04-01T09:00:00")
    d = make_ticket(conn, "fd", company="Initech", score=8, created_at="2026-03-15T09:00:00")
    conn.execute("UPDATE tickets SET score = NULL WHERE id = ?", (d,))
    conn.commit()
    return {"a": a, "b": b, "c": c, "d": d, "rid": rid}


def ids_for(conn, **kw):
    from hireember.web.queries import TicketFilters, list_tickets

    return {r["id"] for r in list_tickets(conn, TicketFilters(**kw))}


def test_filters_narrow_by_company_score_date_resume(conn, tmp_path):
    s = seed_filter_set(conn, tmp_path)
    assert ids_for(conn) == {s["a"], s["b"], s["c"], s["d"]}
    assert ids_for(conn, company="ACME") == {s["a"], s["c"]}
    assert ids_for(conn, score_min=7) == {s["a"], s["c"]}
    assert ids_for(conn, score_max=7) == {s["b"], s["c"]}
    assert ids_for(conn, score_min=5, score_max=9) == {s["a"], s["b"], s["c"]}
    assert ids_for(conn, date_from="2026-03-15", date_to="2026-03-31") == {s["b"], s["d"]}
    assert ids_for(conn, resume_id=s["rid"]) == {s["a"]}
    assert ids_for(conn, company="acme", score_min=8) == {s["a"]}


def test_filter_errors_have_exact_messages(conn):
    from hireember.web.queries import FilterError, TicketFilters, list_tickets

    for bad in (TicketFilters(score_min=101), TicketFilters(score_max=-1)):
        with pytest.raises(FilterError) as exc:
            list_tickets(conn, bad)
        assert str(exc.value) == "Enter a whole number from 0 to 100."
    with pytest.raises(FilterError) as exc:
        list_tickets(conn, TicketFilters(date_from="2026-05-02", date_to="2026-05-01"))
    assert str(exc.value) == "From date must be on or before To date."
    assert issubclass(FilterError, ValueError)


def test_sorting_and_unknown_sort(conn):
    from hireember.web.queries import SORT_COLUMNS, list_tickets

    a = make_ticket(conn, "s1", company="Zed", score=3)
    b = make_ticket(conn, "s2", company="Alpha", score=9)
    assert [r["id"] for r in list_tickets(conn, sort="company", direction="asc")] == [b, a]
    assert [r["id"] for r in list_tickets(conn, sort="score", direction="desc")] == [b, a]
    for col in SORT_COLUMNS:
        list_tickets(conn, sort=col, direction="asc")
    with pytest.raises(ValueError):
        list_tickets(conn, sort="nope")
    with pytest.raises(ValueError):
        list_tickets(conn, direction="sideways")


# -- AC-4: CSV --------------------------------------------------------------

HEADER = ["company", "title", "location", "status", "score", "resume used", "applied date",
          "links", "notes"]


def parse(text):
    return list(csv.reader(io.StringIO(text, newline="")))


def test_csv_header_rows_and_roundtrip(conn, tmp_path):
    from hireember.web.queries import TicketFilters, list_tickets, tickets_csv

    s = seed_filter_set(conn, tmp_path)
    note = 'He said "hi", then\nleft a second line'
    conn.execute("UPDATE tickets SET notes = ?, referral_note = ? WHERE id = ?",
                 (note, "Ask Sam", s["a"]))
    conn.commit()
    text = tickets_csv(conn)
    assert text.split("\r\n")[0] == ",".join(HEADER)
    assert not text.startswith("\ufeff")
    rows = parse(text)
    assert rows[0] == HEADER
    assert len(rows) - 1 == len(list_tickets(conn))
    row_a = next(r for r in rows[1:] if r[0] == "Acme Corp")
    assert row_a[8] == note + "\nReferral: Ask Sam"
    assert row_a[3] == "pending" and row_a[4] == "9" and row_a[5] == "Backend CV"
    assert row_a[7] == "https://jobs.example/fa"
    row_d = next(r for r in rows[1:] if r[0] == "Initech")
    assert row_d[4] == "" and row_d[5] == "" and row_d[6] == "" and row_d[8] == ""

    flt = TicketFilters(company="acme")
    filtered = parse(tickets_csv(conn, flt, sort="score", direction="asc"))
    expected = list_tickets(conn, flt, "score", "asc")
    assert [r[0] for r in filtered[1:]] == [e["company"] for e in expected]
    assert len(filtered) - 1 == 2


def test_csv_empty_view_is_header_only(conn):
    from hireember.web.queries import tickets_csv

    assert parse(tickets_csv(conn)) == [HEADER]


def test_csv_guards_formula_cells(conn):
    from hireember.web.queries import tickets_csv

    t = make_ticket(conn, "formula", company="=SUM(A1)", title="@cmd", location="+1 555")
    conn.execute("UPDATE tickets SET notes = '-2+3' WHERE id = ?", (t,))
    conn.commit()
    row = parse(tickets_csv(conn))[1]
    assert row[0] == "'=SUM(A1)" and row[1] == "'@cmd" and row[2] == "'+1 555"
    assert row[8] == "'-2+3"


# -- AC-6: performance ------------------------------------------------------

def test_list_tickets_5000_under_two_seconds(conn):
    from hireember.web.queries import SORT_COLUMNS, TicketFilters, list_tickets

    seed_many(conn)
    start = time.perf_counter()
    assert len(list_tickets(conn)) == 5000
    assert time.perf_counter() - start < 2
    for col in SORT_COLUMNS:
        start = time.perf_counter()
        list_tickets(conn, sort=col, direction="asc")
        assert time.perf_counter() - start < 2, col
    start = time.perf_counter()
    rows = list_tickets(conn, TicketFilters(company="company 1", score_min=10, score_max=90,
                                            date_from="2026-02-01", date_to="2026-03-31"))
    assert time.perf_counter() - start < 2
    assert 0 < len(rows) < 5000
