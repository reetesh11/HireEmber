"""Company list: add, remove, adoption of job-only companies."""

import pytest

from hireember.companies import (CompanyExistsError, CompanyMissingError, UnknownAtsError,
                                 add_company, remove_company, search_list)
from hireember.tickets import get_or_create_company, list_companies


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_company_known_only_from_jobs_can_be_adopted(conn):
    cid = get_or_create_company(conn, "Seen")
    assert search_list(conn) == []
    assert add_company(conn, "seen", "https://seen.example", "workday") == cid
    assert search_list(conn)[0]["name"] == "Seen"


def test_missing_url_or_type_not_in_search_list(conn):
    conn.execute("INSERT INTO companies (name, careers_url, ats_type) VALUES ('A', '', 'workday')")
    conn.commit()
    assert search_list(conn) == []
    assert list_companies(conn)[0]["ats_type"] == "workday"


def test_errors(conn):
    add_company(conn, "A", "https://a.example", "workday")
    with pytest.raises(CompanyExistsError, match='Company "a" already exists.'):
        add_company(conn, "a", "https://a.example", "workday")
    with pytest.raises(UnknownAtsError):
        add_company(conn, "B", "https://b.example", "x")
    remove_company(conn, "A")
    with pytest.raises(CompanyMissingError, match='Company "A" not found.'):
        remove_company(conn, "A")
