"""Phase 4: `hireember dashboard` command (AC-5, AC-10)."""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("host", ["0.0.0.0", "localhost", "::1", "192.168.0.10"])
def test_dashboard_refuses_other_hosts(host, isolated_db):
    from hireember.cli import app

    result = CliRunner().invoke(app, ["dashboard", "--host", host, "--port", "0"])
    assert result.exit_code == 2, result.output
    expected = f"Refusing to bind to {host}. The dashboard is local only and binds to 127.0.0.1."
    assert expected in " ".join(result.output.split())


def test_dashboard_port_in_use(isolated_db):
    from hireember.cli import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        result = CliRunner().invoke(app, ["dashboard", "--port", str(port)])
    assert result.exit_code == 1, result.output
    assert f"Port {port} is already in use. Choose another with --port." in " ".join(
        result.output.split())


def test_help_lists_dashboard_with_new_text():
    import typer
    from hireember.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "dashboard" in result.output
    assert "Open the local web dashboard." in " ".join(result.output.split())
    cmd = typer.main.get_command(app).commands["dashboard"]
    assert cmd.help.strip().startswith("Open the local web dashboard.")
    opts = {p.name: p for p in cmd.params}
    assert opts["host"].default == "127.0.0.1" and opts["port"].default == 8765
    assert "open" in opts


def test_dashboard_command_starts_server(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src"), PYTHONUNBUFFERED="1",
               HIREEMBER_DIR=str(tmp_path / "data"))
    proc = subprocess.Popen(
        [sys.executable, "-m", "hireember", "dashboard", "--port", str(port)],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        body = None
        deadline = time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                    body = resp.read().decode("utf-8")
                    break
            except OSError:
                time.sleep(0.3)
        assert body is not None and "HireEmber" in body
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            out, _ = proc.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
    assert (f"HireEmber dashboard running at http://127.0.0.1:{port} (local only). "
            "Press Ctrl+C to stop.") in out
