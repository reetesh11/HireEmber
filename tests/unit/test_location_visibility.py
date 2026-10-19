from rich.console import Console
from typer.testing import CliRunner

import hireember.cli as cli
from hireember import config, tickets
from hireember.database import close_connection, get_stats, init_db, store_jobs


def test_stats_status_and_log(isolated_db, monkeypatch):
    monkeypatch.setattr(cli, "console", Console(width=200))
    conn = init_db(isolated_db)
    config.ensure_dirs()
    store_jobs(conn, [{"url": "a", "title": "T", "company": "C", "location": "Berlin"},
                      {"url": "b", "title": "T", "company": "C", "location": "Paris"}], "S", "t")
    t = tickets.open_ticket(conn, "a", "skipped", "location: Berlin")
    tickets.open_ticket(conn, "b", "skipped", "score 2 below threshold 7")
    assert get_stats(conn)["location_skipped"] == 1
    status = CliRunner().invoke(cli.app, ["status"])
    assert "Skipped by location" in status.output
    log = CliRunner().invoke(cli.app, ["ticket", "log", str(t)])
    assert "Status: skipped (location: Berlin)" in log.output
    close_connection(isolated_db)
