"""Phase 7 AC-1: POST /api/resumes creates a resume from .pdf, .txt or .docx; bad uploads store nothing."""

import json

import pytest

from p7_helpers import (MB10, RESUME_TEXT, Client, base_dir, blank_pdf_bytes, docx_bytes, post_multipart,
                        post_raw, row_count, start_server, stop_server, stored_files)

UNSUPPORTED = "Unsupported format. Provide a .pdf, .txt or .docx file."


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
def test_txt_upload_creates_resume(env, poster):
    conn, client = env
    status, body = poster(client, "cv.txt", RESUME_TEXT.encode(), f"Txt {poster.__name__}", "Backend, Python")
    assert status == 201, body
    assert body["name"] == f"Txt {poster.__name__}"
    assert body["tags"] == ["backend", "python"]
    assert body["pinned"] is False
    assert body["extract_status"] == "extracted"
    assert body["chunk_count"] >= 1
    assert body["file_name"].endswith(".txt")
    assert (base_dir() / body["file_name"]).is_file()
    status, listing = client.get("/api/resumes")
    assert status == 200
    assert body["id"] in [r["id"] for r in listing["resumes"]]


@pytest.mark.parametrize("poster", [post_raw, post_multipart])
def test_docx_upload_creates_resume(env, poster):
    conn, client = env
    data = docx_bytes(["Summary", "Python developer.", "Skills", "Python, SQL"])
    status, body = poster(client, "CV.DOCX", data, f"Docx {poster.__name__}")
    assert status == 201, body
    assert body["file_name"].endswith(".docx")
    assert body["extract_status"] == "extracted"
    assert body["chunk_count"] >= 1


def test_pdf_upload_creates_resume(env):
    conn, client = env
    status, body = post_raw(client, "cv.pdf", blank_pdf_bytes(), "Pdf one")
    assert status == 201, body
    assert body["file_name"].endswith(".pdf")
    assert body["extract_status"] == "no_text"
    assert body["chunk_count"] == 0


@pytest.mark.parametrize("poster", [post_raw, post_multipart])
@pytest.mark.parametrize("filename", ["cv.doc", "cv.docx.exe", "cv", "cv.rtf"])
def test_bad_extension_refused_and_nothing_stored(env, poster, filename):
    conn, client = env
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = poster(client, filename, b"some content", "Bad ext")
    assert status == 400
    assert body == {"error": UNSUPPORTED}
    assert stored_files() == before_files and row_count(conn) == before_rows


@pytest.mark.parametrize("poster", [post_raw, post_multipart])
def test_empty_file_refused(env, poster):
    conn, client = env
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = poster(client, "cv.txt", b"", "Empty one")
    assert status == 400
    assert body == {"error": "The file is empty."}
    assert stored_files() == before_files and row_count(conn) == before_rows


def test_exactly_10_mb_accepted(env):
    conn, client = env
    data = (b"python experience line\n" * (MB10 // 23 + 1))[:MB10]
    assert len(data) == MB10
    status, body = post_raw(client, "big.txt", data, "Exactly ten")
    assert status == 201, body


def test_over_10_mb_refused_within_margin(env):
    conn, client = env
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = post_raw(client, "big.txt", b"a" * (MB10 + 1), "Too big")
    assert status == 400
    assert body == {"error": "The file is larger than 10 MB."}
    assert stored_files() == before_files and row_count(conn) == before_rows


def test_far_over_10_mb_refused_with_413(env):
    conn, client = env
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = post_raw(client, "huge.txt", b"a" * (MB10 + 65 * 1024 + 1), "Way too big")
    assert status == 413
    assert body == {"error": "The file is larger than 10 MB."}
    assert stored_files() == before_files and row_count(conn) == before_rows


@pytest.mark.parametrize("poster", [post_raw, post_multipart])
def test_blank_name_refused(env, poster):
    conn, client = env
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = poster(client, "cv.txt", b"text", "   ")
    assert status == 400
    assert body == {"error": "Name cannot be empty."}
    assert stored_files() == before_files and row_count(conn) == before_rows


def test_duplicate_name_refused(env):
    conn, client = env
    assert post_raw(client, "a.txt", b"first", "Same Name")[0] == 201
    before_files, before_rows = stored_files(), row_count(conn)
    status, body = post_raw(client, "b.txt", b"second", "same name")
    assert status == 400
    assert body == {"error": 'A resume named "same name" already exists.'}
    assert stored_files() == before_files and row_count(conn) == before_rows


def test_validation_order_extension_before_empty(env):
    conn, client = env
    status, body = post_raw(client, "cv.exe", b"", "")
    assert status == 400 and body == {"error": UNSUPPORTED}


def test_several_uploads_one_after_another(env):
    conn, client = env
    ids = []
    for i in range(3):
        status, body = post_raw(client, "cv.txt", f"Skills\nPython {i}".encode(), f"Multi {i}")
        assert status == 201, body
        ids.append(body["id"])
    status, listing = client.get("/api/resumes")
    assert set(ids) <= {r["id"] for r in listing["resumes"]}
    assert len(set(ids)) == 3


def test_non_utf8_txt_is_accepted(env):
    conn, client = env
    status, body = post_raw(client, "cv.txt", b"Skills\nPython caf\xe9 \xff\xfe", "Latin one")
    assert status == 201, body
    assert body["extract_status"] == "extracted"


def test_response_is_json(env):
    conn, client = env
    status, headers, payload = client.request(
        "POST", "/api/resumes", headers={"X-Filename": "cv.txt", "X-Name": "Json one"}, raw=b"hello world")
    assert status == 201
    assert "json" in {k.lower(): v for k, v in headers.items()}["content-type"]
    assert json.loads(payload)["name"] == "Json one"
