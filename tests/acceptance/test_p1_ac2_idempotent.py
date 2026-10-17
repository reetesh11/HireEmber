"""AC-2: a second migration changes nothing, for both database file names."""

import pytest

from hireember.database import close_connection, init_db

from p1_helpers import count, make_legacy_db, table_names


@pytest.mark.parametrize("name", ["applypilot.db", "hireember.db"])
def test_second_migration_is_a_no_op(tmp_path, name):
    from hireember.migration import migrate_database

    db = tmp_path / name
    make_legacy_db(db)
    try:
        assert migrate_database(db) is not None
        conn = init_db(db)
        before = (table_names(conn), count(conn, "tickets"), count(conn, "ticket_events"),
                  count(conn, "jobs"))
        backups = sorted(p.name for p in tmp_path.glob(name + ".bak-*"))
        assert len(backups) == 1
        close_connection(db)

        assert migrate_database(db) is None
        conn = init_db(db)
        after = (table_names(conn), count(conn, "tickets"), count(conn, "ticket_events"),
                 count(conn, "jobs"))
        assert after == before
        assert sorted(p.name for p in tmp_path.glob(name + ".bak-*")) == backups
        assert (tmp_path / name).exists()
    finally:
        close_connection(db)
