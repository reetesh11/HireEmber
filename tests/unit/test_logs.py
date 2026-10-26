"""Unit tests for the log writer."""

import os
from datetime import datetime, timedelta, timezone

from hireember import config, logs


def test_write_and_read_single_line(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    path = logs.run_log_path(5)
    assert logs.write_line(path, "a\nb", "warn")
    assert logs.read_log(path).strip().endswith("[warn] a b")
    assert logs.read_log(tmp_path / "missing.log") is None


def test_redacts_long_secret_values(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    monkeypatch.setenv("MY_API_KEY", "supersecretvalue")
    path = logs.run_log_path(1)
    logs.write_line(path, "leak supersecretvalue")
    assert "supersecretvalue" not in logs.read_log(path)


def test_unwritable_folder_returns_false(tmp_path, monkeypatch):
    blocker = tmp_path / "f"
    blocker.write_text("x")
    monkeypatch.setattr(config, "LOG_DIR", blocker / "logs")
    assert logs.write_line(logs.run_log_path(1), "x") is False


def test_prune_by_age(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    old, new, other = logs.run_log_path(1), logs.attempt_log_path(1, 1), tmp_path / "worker-1.log"
    for p, days in ((old, 91), (new, 89), (other, 300)):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
        stamp = (now - timedelta(days=days)).timestamp()
        os.utime(p, (stamp, stamp))
    assert logs.prune_logs(now=now) == 1
    assert not old.exists() and new.exists() and other.exists()
