import pytest

from hireember.database import close_connection, init_db, store_jobs
from hireember.tickets import (
    CompanyNotFoundError,
    get_history,
    get_setting,
    get_ticket,
    is_manual_company,
    list_companies,
    set_company_manual,
    set_job_score,
    set_reason,
    set_setting,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "hireember.db"
    c = init_db(db)
    store_jobs(c, [{"url": "u1", "title": "T", "company": "Acme", "location": "X"}], "S", "t")
    yield c
    close_connection(db)


def test_get_setting_default(conn):
    assert get_setting(conn, "nope") is None
    assert get_setting(conn, "nope", "5") == "5"
    set_setting(conn, "k", "v")
    assert get_setting(conn, "k", "5") == "v"


def test_set_company_manual_is_case_insensitive(conn):
    cid = set_company_manual(conn, "  aCmE ")
    assert [c for c in list_companies(conn) if c["id"] == cid][0]["manual_only"] is True
    set_company_manual(conn, "ACME", False)
    assert list_companies(conn)[0]["manual_only"] is False


def test_unknown_company_raises(conn):
    with pytest.raises(CompanyNotFoundError) as exc:
        set_company_manual(conn, "Nobody")
    assert str(exc.value) == 'No company named "Nobody".'


def test_is_manual_company_follows_company_and_site_fallback(conn):
    tid = set_job_score(conn, "u1", 8)
    assert is_manual_company(conn, tid) is False
    set_company_manual(conn, "acme")
    assert is_manual_company(conn, tid) is True
    conn.execute("UPDATE jobs SET company_id = NULL, site = 'Acme' WHERE url = 'u1'")
    conn.commit()
    assert is_manual_company(conn, tid) is True
    conn.execute("UPDATE jobs SET site = 'Other' WHERE url = 'u1'")
    conn.commit()
    assert is_manual_company(conn, tid) is False


def test_set_reason_writes_event_only_on_change(conn):
    tid = set_job_score(conn, "u1", 8)
    n = len(get_history(conn, tid))
    set_reason(conn, tid, "limit: daily", not_before="2026-01-01T00:00:00+00:00")
    set_reason(conn, tid, "limit: daily", not_before="2026-01-02T00:00:00+00:00")
    t = get_ticket(conn, tid)
    assert t["status"] == "pending" and t["not_before"].startswith("2026-01-02")
    assert len(get_history(conn, tid)) == n + 1
