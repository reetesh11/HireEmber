import os
import sqlite3
import stat
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "acceptance"))

from p1_helpers import make_legacy_db  # noqa: E402

from hireember.database import close_connection, init_db  # noqa: E402
from hireember.migration import (  # noqa: E402
    MigrationError,
    backup_if_needed,
    migrate_database,
    needs_migration,
)


def test_fresh_db_no_backup_and_second_call_no_backup(tmp_path):
    db = tmp_path / "hireember.db"
    try:
        assert migrate_database(db) is None
        assert not needs_migration(db)
        assert migrate_database(db) is None
        assert list(tmp_path.glob("*.bak-*")) == []
    finally:
        close_connection(db)


def test_backup_contains_original_rows_and_collision_gets_new_name(tmp_path):
    db = tmp_path / "applypilot.db"
    make_legacy_db(db)
    first = backup_if_needed(db)
    second = backup_if_needed(db)
    assert first != second and first.exists() and second.exists()
    assert first.name.startswith("applypilot.db.bak-")
    conn = sqlite3.connect(str(first))
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 10
    conn.close()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_backup_failure_leaves_database_unchanged(tmp_path):
    db = tmp_path / "hireember.db"
    make_legacy_db(db)
    before = db.read_bytes()
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(MigrationError, match="^Backup failed; the database was not changed:"):
            init_db(db)
    finally:
        tmp_path.chmod(stat.S_IRWXU)
        close_connection(db)
    assert db.read_bytes() == before
    assert list(tmp_path.glob("*.bak-*")) == []
