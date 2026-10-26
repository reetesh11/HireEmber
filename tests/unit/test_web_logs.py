"""Dashboard log routes and the ticket extras section."""

from hireember import config, logs
from hireember.database import init_db
from hireember.web import queries


def test_runs_html_links_or_says_removed(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    conn = init_db()
    conn.execute("INSERT INTO runs (kind, \"trigger\", status, started_at) "
                 "VALUES ('full', 'manual', 'completed', '2026-01-01')")
    conn.commit()
    rid = conn.execute("SELECT id FROM runs").fetchone()[0]
    assert "Log removed" in queries.runs_html(conn, True)
    logs.write_line(logs.run_log_path(rid), "hi")
    assert f'<a href="/logs/runs/{rid}">Log</a>' in queries.runs_html(conn, True)


def test_ticket_extras_without_attempts(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    conn = init_db()
    html = queries.ticket_extras_html(conn, 1, True)
    assert "No attempt log yet." in html and "<html" not in html
    assert queries.ticket_logs(conn, 1) == []
