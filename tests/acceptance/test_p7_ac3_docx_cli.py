"""Phase 7 AC-3: .docx support in the CLI and extractor, help text, dependency declared."""

import re

import pytest
import typer.main
from typer.testing import CliRunner

from p2_helpers import widen_cli_console
from p7_helpers import REPO_ROOT, docx_bytes

UNSUPPORTED = "Unsupported format. Provide a .pdf, .txt or .docx file."


@pytest.fixture
def env(isolated_db, monkeypatch):
    from hireember import config
    from hireember.database import close_connection, init_db

    conn = init_db()
    config.ensure_dirs()
    widen_cli_console(monkeypatch)
    yield conn
    close_connection(isolated_db)


def _resume_cmd(name):
    from hireember.cli import app

    group = typer.main.get_command(app).commands["resume"]
    return group if name is None else group.commands[name]


def test_cli_adds_docx_and_reports_chunks(env, tmp_path):
    from hireember.cli import app

    path = tmp_path / "cv.docx"
    path.write_bytes(docx_bytes(["Summary", "Backend engineer.", "Skills", "Python, SQL"]))
    res = CliRunner().invoke(app, ["resume", "add", str(path), "--name", "Docx CV", "--tags", "backend"])
    assert res.exit_code == 0, res.output
    assert re.search(r"Added resume \d+: Docx CV\.", res.output)
    assert re.search(r"Extracted \d+ chunks\.", res.output)


def test_cli_corrupt_docx_is_added_with_failure_line(env, tmp_path):
    from hireember.cli import app
    from hireember.resumes import list_resumes

    path = tmp_path / "bad.docx"
    path.write_bytes(b"this is not a zip file")
    res = CliRunner().invoke(app, ["resume", "add", str(path), "--name", "Broken"])
    assert res.exit_code == 0, res.output
    assert "Added, but no text could be extracted: this .docx file could not be read." in res.output
    row = [r for r in list_resumes(env) if r["name"] == "Broken"][0]
    assert row["extract_status"] == "failed"
    assert row["chunk_count"] == 0


def test_cli_unsupported_extension(env, tmp_path):
    from hireember.cli import app

    path = tmp_path / "cv.doc"
    path.write_bytes(b"x")
    res = CliRunner().invoke(app, ["resume", "add", str(path), "--name", "Old"])
    assert res.exit_code == 1
    assert UNSUPPORTED in res.output


def test_cli_help_texts(env):
    assert _resume_cmd(None).help == "Base resumes (.pdf, .txt, .docx) used for scoring and tailoring."
    add = _resume_cmd("add")
    assert add.help.strip() == "Add a base resume (.pdf, .txt or .docx)."
    file_param = [p for p in add.params if p.name == "file"][0]
    assert file_param.help == "Resume file (.pdf, .txt or .docx)."


def test_cli_callback_docstring_lists_formats(env):
    from hireember.cli import resume_add

    assert resume_add.__doc__.strip() == "Add a base resume (.pdf, .txt or .docx)."


def test_extract_docx_text_paragraphs_and_tables_in_order(tmp_path):
    from hireember.resume_extract import extract_docx_text

    path = tmp_path / "cv.docx"
    path.write_bytes(docx_bytes(["Intro line", [["Company", "Role"], ["Acme", "Engineer"]], "Closing line"]))
    lines = extract_docx_text(path).splitlines()
    lines = [ln for ln in lines if ln.strip()]
    assert lines == ["Intro line", "Company\tRole", "Acme\tEngineer", "Closing line"]


def test_extract_docx_text_corrupt_raises_value_error(tmp_path):
    from hireember.resume_extract import extract_docx_text

    path = tmp_path / "bad.docx"
    path.write_bytes(b"not a docx at all")
    with pytest.raises(ValueError) as exc:
        extract_docx_text(path)
    assert str(exc.value) == "this .docx file could not be read."


def test_docx_dependency_declared_in_pyproject_and_lock():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert re.search(r"python-docx", pyproject, re.IGNORECASE)
    assert re.search(r'name = "python-docx"', lock)
