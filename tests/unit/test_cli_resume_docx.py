"""CLI resume add/list/delete with extraction (implementation tests)."""

import pytest
from typer.testing import CliRunner

from hireember import config
from hireember.cli import app
from hireember.database import close_connection, init_db


@pytest.fixture
def conn(isolated_db):
    c = init_db()
    config.ensure_dirs()
    yield c
    close_connection(isolated_db)


def test_add_reports_chunks_or_failure_and_delete(conn, tmp_path):
    ok = tmp_path / "a.txt"
    ok.write_text("Skills\nPython", encoding="utf-8")
    res = CliRunner().invoke(app, ["resume", "add", str(ok), "--name", "Ok"])
    assert res.exit_code == 0 and "Added resume 1: Ok." in res.output and "Extracted 1 chunks." in res.output
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"junk")
    res = CliRunner().invoke(app, ["resume", "add", str(bad), "--name", "Bad"])
    assert res.exit_code == 0
    assert "Added, but no text could be extracted: this .docx file could not be read." in res.output
    res = CliRunner().invoke(app, ["resume", "delete", "1"])
    assert res.exit_code == 0 and "Deleted resume 1." in res.output
    res = CliRunner().invoke(app, ["resume", "delete", "1"])
    assert res.exit_code == 1 and "No resume with id 1." in res.output
