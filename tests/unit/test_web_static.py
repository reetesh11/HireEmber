"""The dashboard page (implementation tests)."""

from pathlib import Path

import hireember.web

PAGE = (Path(hireember.web.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


def test_required_strings():
    for text in ("<title>HireEmber", "Tickets", "Blocked (", "Answers", "Resumes", "Board", "List",
                 "Min score", "Max score", "Clear filters", "Export CSV", "Change status",
                 "Save note", "Save referral note", "Override reason", "No tickets",
                 "No link available", "Copy path", "Reconnecting...", "Live",
                 "Loading tickets...", "Could not load tickets.",
                 "No tickets match these filters.", "Nothing is blocked. You're all caught up.",
                 "Merge these two answers into one? The other entry will be deleted.",
                 "Delete this answer? This cannot be undone.",
                 "No stored answers yet. Answers you give are saved here.",
                 "No resumes yet. Add one with 'hireember resume add'."):
        assert text in PAGE, text


def test_no_inner_html_and_polls_updates():
    assert "innerHTML" not in PAGE and "insertAdjacentHTML" not in PAGE
    assert "/api/updates" in PAGE and "setInterval(poll, 2000)" in PAGE


def test_served_at_root(tmp_path):
    from hireember.web.server import create_server
    import http.client
    import threading

    server = create_server("127.0.0.1", 0, db_path=tmp_path / "x.db")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        c.request("GET", "/")
        assert c.getresponse().read().decode("utf-8") == PAGE
    finally:
        server.shutdown()
        server.server_close()
