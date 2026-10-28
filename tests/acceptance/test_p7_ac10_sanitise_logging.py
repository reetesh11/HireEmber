"""Phase 7 AC-10: filenames are sanitised; resume text never reaches logs or error bodies."""

import json
import logging
from pathlib import Path

import pytest

from p7_helpers import (Client, base_dir, docx_bytes, post_multipart, post_raw, start_server, stop_server,
                        text_file)

SECRET = "ZEBRAQUILL7391"


@pytest.fixture
def env(isolated_db):
    from hireember import config
    from hireember.database import close_connection, init_db

    conn = init_db()
    config.ensure_dirs()
    server, thread = start_server(isolated_db)
    yield conn, Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


@pytest.mark.parametrize("poster", [post_raw, post_multipart])
@pytest.mark.parametrize("filename,suffix", [
    ("../../x.pdf", ".pdf"), ("..\\..\\x.docx", ".docx"), ("C:\\a\\b.docx", ".docx"),
    ("/etc/passwd.txt", ".txt"), ("a/b/../../../../evil.txt", ".txt")])
def test_http_upload_stays_inside_base_resume_folder(env, poster, filename, suffix):
    from hireember import config

    conn, client = env
    data = docx_bytes(["Skills", "Python"]) if suffix == ".docx" else b"Skills\nPython"
    name = f"San {poster.__name__} {abs(hash(filename)) % 10000}"
    before = {p for p in config.APP_DIR.rglob("*") if p.is_file()}
    status, body = poster(client, filename, data, name)
    assert status == 201, body
    assert body["file_name"] == Path(body["file_name"]).name
    assert body["file_name"].endswith(suffix)
    assert (base_dir() / body["file_name"]).is_file()
    new = {p for p in config.APP_DIR.rglob("*") if p.is_file()} - before
    assert new and all(base_dir().resolve() in p.resolve().parents for p in new)
    assert not any(p.name in ("x.pdf", "x.docx", "passwd.txt", "evil.txt", "b.docx") for p in new)
    assert not (config.APP_DIR.parent / "x.pdf").exists()


def test_stored_name_derives_from_resume_name_not_client_filename(env):
    conn, client = env
    status, body = post_raw(client, "secret_client_name.txt", b"Skills\nPython", "My Fancy Resume")
    assert status == 201
    assert "secret_client_name" not in body["file_name"]
    assert body["file_name"].startswith("my_fancy_resume")


def test_add_resume_bytes_drops_directory_parts(env):
    from hireember.resumes import add_resume_bytes, list_resumes

    conn, _ = env
    rid = add_resume_bytes(conn, "../../x.pdf", b"%PDF-1.4\n%%EOF\n", "Bytes one")
    path = Path([r for r in list_resumes(conn) if r["id"] == rid][0]["file_path"])
    assert path.parent.resolve() == base_dir().resolve() and path.suffix == ".pdf"
    rid2 = add_resume_bytes(conn, "C:\\a\\b.docx", docx_bytes(["Skills", "Python"]), "Bytes two")
    path2 = Path([r for r in list_resumes(conn) if r["id"] == rid2][0]["file_path"])
    assert path2.parent.resolve() == base_dir().resolve() and path2.suffix == ".docx"


def test_add_resume_bytes_validation_order_and_messages(env):
    from hireember.resumes import ResumeError, add_resume_bytes

    conn, _ = env
    add_resume_bytes(conn, "a.txt", b"hello", "Order one")
    before = set(base_dir().iterdir())
    cases = [
        (("a.exe", b"", ""), "Unsupported format. Provide a .pdf, .txt or .docx file."),
        (("a.txt", b"", ""), "The file is empty."),
        (("a.txt", b"x" * (10 * 1024 * 1024 + 1), ""), "The file is larger than 10 MB."),
        (("a.txt", b"x", "  "), "Name cannot be empty."),
        (("a.txt", b"x", "order ONE"), 'A resume named "order ONE" already exists.'),
    ]
    for (fn, data, name), message in cases:
        with pytest.raises(ResumeError) as exc:
            add_resume_bytes(conn, fn, data, name)
        assert str(exc.value) == message
    assert set(base_dir().iterdir()) == before


def _secret_doc():
    return f"Summary\n{SECRET} lives here.\n\nSkills\n{SECRET} Python".encode()


def test_resume_text_is_not_logged_at_info_or_above(env, tmp_path, caplog):
    from hireember.resumes import (add_resume, add_resume_bytes, delete_resume, extract_resume, search,
                                   update_resume)

    conn, client = env
    caplog.set_level(logging.INFO)
    rid = add_resume(conn, text_file(tmp_path, _secret_doc().decode()), "Log one")
    add_resume_bytes(conn, "d.docx", docx_bytes(["Skills", SECRET]), "Log two")
    bad = tmp_path / "bad.docx"
    bad.write_bytes(b"corrupt " + SECRET.encode())
    add_resume(conn, bad, "Log bad")
    post_raw(client, "a.txt", _secret_doc(), "Log http")
    post_raw(client, "a.txt", _secret_doc(), "Log http")  # duplicate -> error path
    post_raw(client, "a.exe", _secret_doc(), "Log exe")
    update_resume(conn, rid, text_file(tmp_path, _secret_doc().decode()))
    extract_resume(conn, rid)
    search(conn, SECRET)
    delete_resume(conn, rid)
    assert SECRET not in caplog.text
    for record in caplog.records:
        assert SECRET not in record.getMessage()


def test_error_bodies_and_reasons_do_not_echo_content(env, tmp_path):
    from hireember.resumes import add_resume, list_resumes

    conn, client = env
    for filename, data in (("a.exe", _secret_doc()), ("a.txt", b"")):
        status, body = post_raw(client, filename, data, "Err one")
        assert status == 400 and SECRET not in json.dumps(body)
    status, created = post_raw(client, "bad.docx", b"corrupt " + SECRET.encode(), "Err bad")
    assert status == 201
    assert SECRET not in json.dumps(created)
    assert "Traceback" not in json.dumps(created)
    status, body = client.json("POST", f"/api/resumes/{created['id']}/extract", {})
    assert status == 200 and SECRET not in json.dumps(body) and "Traceback" not in json.dumps(body)
    bad = tmp_path / "bad2.docx"
    bad.write_bytes(b"corrupt " + SECRET.encode())
    rid = add_resume(conn, bad, "Err bad two")
    reason = [r for r in list_resumes(conn) if r["id"] == rid][0]["extract_reason"]
    assert reason and SECRET not in reason
