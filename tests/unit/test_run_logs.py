"""Run and attempt logs are written next to the database rows."""

from hireember import config, logs, runs
from hireember.apply import attempts
from hireember.database import init_db


def test_log_step_mirrors_to_file(isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    conn = init_db()
    attempts.log_step(conn, 1, 1, "fill", field="email", source="profile", detail="typed")
    text = logs.read_log(logs.attempt_log_path(1, 1))
    assert text.strip().endswith("fill | field=email | source=profile | typed")


def test_log_event_mirrors_to_file_and_survives_unwritable_dir(isolated_db, tmp_path, monkeypatch):
    conn = init_db()
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    runs.log_event(conn, 3, "score", "bad", "error")
    assert "[error] score: bad" in logs.read_log(logs.run_log_path(3))
    blocker = tmp_path / "f"
    blocker.write_text("x")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")
    runs.log_event(conn, 4, "score", "still fine", "error")
    assert runs.get_run_log(conn, 4)[0]["message"] == "still fine"
