"""Shared pytest harness for ApplyPilot.

Isolation rules (applied at import time, before any ``applypilot`` import):

- ``APPLYPILOT_DIR`` points at a fresh temporary directory, so
  ``applypilot.config`` never reads or writes the real ``~/.applypilot``.
- ``CHROME_PATH`` is removed so Chrome detection is not driven by the
  developer's shell.

Fixtures:

- ``fixture_form_server``: serves ``tests/fixtures/`` from a local
  ``http.server.ThreadingHTTPServer`` on ``127.0.0.1`` and yields its base URL.
- ``isolated_db``: points the default database path at a temp file.
"""

from __future__ import annotations

import atexit
import functools
import http.server
import os
import shutil
import tempfile
import threading
from pathlib import Path

import pytest

_TEST_APP_DIR = tempfile.mkdtemp(prefix="applypilot-tests-")
os.environ["APPLYPILOT_DIR"] = _TEST_APP_DIR
os.environ.pop("CHROME_PATH", None)
atexit.register(shutil.rmtree, _TEST_APP_DIR, True)

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def fixture_form_server():
    """Serve tests/fixtures/ on 127.0.0.1 (ephemeral port); yield the base URL."""
    handler = functools.partial(_QuietHandler, directory=str(FIXTURES_DIR))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the default DB (database and config modules) at a temp file; yield its path.

    The file is not created; call ``applypilot.database.init_db()`` if a schema is needed.
    """
    import applypilot.config
    import applypilot.database

    db_path = tmp_path / "applypilot.db"
    monkeypatch.setattr(applypilot.database, "DB_PATH", db_path)
    monkeypatch.setattr(applypilot.config, "DB_PATH", db_path)
    yield db_path
    applypilot.database.close_connection(db_path)
