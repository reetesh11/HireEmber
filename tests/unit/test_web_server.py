"""Dashboard HTTP server: guards and read-only routes (implementation tests)."""

import http.client
import json
import threading

import pytest

from hireember.database import close_connection, init_db
from hireember.web.server import HostRefusedError, create_server


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "hireember.db"
    conn = init_db(db)
    server = create_server("127.0.0.1", 0, db_path=db)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield conn, server.server_address[1]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    close_connection(db)


def get(port, path, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers=headers or {})
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, dict(r.getheaders()), body


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "::1"])
def test_other_hosts_refused(host):
    with pytest.raises(HostRefusedError):
        create_server(host, 0)


def test_routes_shapes_and_guard(env):
    _, port = env
    status, headers, body = get(port, "/")
    assert status == 200 and b"HireEmber" in body
    for path, key in (("/api/tickets", "tickets"), ("/api/blocked", "items"),
                      ("/api/answers", "answers"), ("/api/resumes", "resumes"),
                      ("/api/updates", "cursor")):
        status, _, body = get(port, path)
        assert status == 200 and key in json.loads(body), path
    assert get(port, "/api/nope")[0] == 404
    assert get(port, "/api/tickets/1")[0] == 404
    assert get(port, "/api/tickets", {"Host": "evil.example"})[0] == 403


def test_csv_bom_and_filename(env):
    _, port = env
    status, headers, body = get(port, "/api/export.csv")
    assert status == 200 and body.startswith(b"\xef\xbb\xbfcompany,title")
    assert "hireember-tickets-" in headers["Content-Disposition"]
