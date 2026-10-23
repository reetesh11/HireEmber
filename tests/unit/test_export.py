"""CSV export: files, overwrite, and the formula guard on run values."""

import csv
import io

import pytest

from hireember.export import ExportError, export_csv


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


def test_header_only_and_overwrite(conn, tmp_path):
    first = export_csv(conn, tmp_path)
    assert [n for _, n in first] == [0, 0]
    (tmp_path / "runs.csv").write_text("stale")
    export_csv(conn, tmp_path)
    assert (tmp_path / "runs.csv").read_text().startswith("id,kind,trigger")


def test_run_values_are_guarded(conn, tmp_path):
    conn.execute('INSERT INTO runs (kind, "trigger", status, started_at) '
                 "VALUES ('full', '=cmd', 'completed', '2026-01-01')")
    conn.commit()
    export_csv(conn, tmp_path)
    rows = list(csv.DictReader(io.StringIO((tmp_path / "runs.csv").read_text())))
    assert rows[0]["trigger"].startswith("'") or not rows[0]["trigger"].startswith("=")


def test_not_a_folder(conn, tmp_path):
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(ExportError):
        export_csv(conn, f)
