"""The user-maintained company list: what discovery searches."""

from __future__ import annotations

import sqlite3

from hireember.tickets import TicketError

ATS_TYPES = ("workday", "careers-page")


class CompanyExistsError(TicketError):
    """An active company with this name is already on the list."""

    def __init__(self, name: str):
        super().__init__(f'Company "{name}" already exists.')


class CompanyMissingError(TicketError):
    """No active company with this name."""

    def __init__(self, name: str):
        super().__init__(f'Company "{name}" not found.')


class UnknownAtsError(TicketError, ValueError):
    """The ATS type is not one discovery can search."""

    def __init__(self, value: str):
        super().__init__(f'Unknown ATS type "{value}". Valid types: {", ".join(ATS_TYPES)}.')


def _find(conn: sqlite3.Connection, name: str, active: bool | None = None):
    sql = ("SELECT id, careers_url, ats_type, COALESCE(active, 1) FROM companies "
           "WHERE lower(trim(name)) = ?")
    if active is not None:
        sql += " AND COALESCE(active, 1) = ?"
    rows = conn.execute(sql + " ORDER BY id", (name.strip().lower(), *(() if active is None else (1 if active else 0,))))
    return rows.fetchall()


def add_company(conn: sqlite3.Connection, name: str, careers_url: str, ats_type: str) -> int:
    """Add a company to the search list and return its id; reactivate a removed one."""
    clean = (name or "").strip()
    if ats_type not in ATS_TYPES:
        raise UnknownAtsError(ats_type)
    for row in _find(conn, clean, active=True):
        if row[1] or row[2]:
            raise CompanyExistsError(clean)
        target = row[0]  # known only from its jobs so far: give it a URL and type
        break
    else:
        inactive = _find(conn, clean, active=False)
        if inactive:
            target = inactive[0][0]
        else:
            cur = conn.execute("INSERT INTO companies (name, careers_url, ats_type, active) "
                               "VALUES (?, ?, ?, 1)", (clean, careers_url, ats_type))
            conn.commit()
            return cur.lastrowid
    conn.execute("UPDATE companies SET careers_url = ?, ats_type = ?, active = 1 WHERE id = ?",
                 (careers_url, ats_type, target))
    conn.commit()
    return target


def remove_company(conn: sqlite3.Connection, name: str) -> None:
    """Take a company off the list (soft: tickets that join to it keep its name)."""
    rows = _find(conn, name or "", active=True)
    if not rows:
        raise CompanyMissingError((name or "").strip())
    conn.execute("UPDATE companies SET active = 0 WHERE id = ?", (rows[0][0],))
    conn.commit()


def search_list(conn: sqlite3.Connection) -> list[dict]:
    """Active companies that have a careers URL and an ATS type."""
    rows = conn.execute(
        "SELECT id, name, careers_url, ats_type FROM companies "
        "WHERE COALESCE(active, 1) = 1 AND COALESCE(trim(careers_url), '') != '' "
        "AND COALESCE(trim(ats_type), '') != '' ORDER BY lower(name), id").fetchall()
    return [{"id": r[0], "name": r[1], "careers_url": r[2], "ats_type": r[3]} for r in rows]
