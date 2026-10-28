"""Dashboard resume upload, extract and delete routes (implementation tests)."""

import http.client
import json
from urllib.parse import quote

import pytest

from hireember import config
from hireember.database import close_connection, init_db
from hireember.web.server import DashboardServer, _parse_multipart


@pytest.fixture
def api(tmp_path):
    import threading

    db = tmp_path / "hireember.db"
    conn = init_db(db)
    config.ensure_dirs()
    server = DashboardServer(("127.0.0.1", 0), db)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def call(method, path, body=b"", headers=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, json.loads(data)

    yield call
    server.shutdown()
    server.server_close()
    thread.join()
    close_connection(db)
    conn.close()


def test_raw_create_extract_delete(api):
    status, body = api("POST", "/api/resumes", b"Skills\nPython",
                       {"X-Filename": "cv.txt", "X-Name": quote("Résumé"), "X-Tags": "a"})
    assert status == 201 and body["name"] == "Résumé" and body["extract_status"] == "extracted"
    status, out = api("POST", f"/api/resumes/{body['id']}/extract")
    assert status == 200 and out["ok"] is True and out["message"] == "Extraction finished: 1 chunks."
    assert api("POST", "/api/resumes/99/extract")[0] == 404
    assert api("DELETE", f"/api/resumes/{body['id']}")[0] == 200
    assert api("DELETE", f"/api/resumes/{body['id']}")[0] == 404


def test_refusals_are_plain_errors(api):
    assert api("POST", "/api/resumes", b"x", {"X-Filename": "a.exe", "X-Name": "n"}) == (
        400, {"error": "Unsupported format. Provide a .pdf, .txt or .docx file."})
    assert api("POST", "/api/resumes", b"", {"X-Filename": "a.txt", "X-Name": "n"})[1] == {
        "error": "The file is empty."}


def test_parse_multipart():
    body = (b'--b\r\nContent-Disposition: form-data; name="name"\r\n\r\nMy CV\r\n'
            b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\nhello\r\n--b--\r\n')
    parts = _parse_multipart("multipart/form-data; boundary=b", body)
    assert parts["name"][1] == b"My CV" and parts["file"] == ("a.txt", b"hello")
