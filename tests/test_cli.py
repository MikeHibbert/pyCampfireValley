import subprocess
import sys
from pathlib import Path


def run_cli(args):
    cmd = [sys.executable, "-m", "campfirevalley.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True)


def test_cli_help():
    res = run_cli(["-h"])
    assert res.returncode == 0
    assert "campfirevalley start" in res.stdout or "Start a valley instance" in res.stdout


def test_cli_has_onboard_and_daemon_status(tmp_path, monkeypatch):
    # Run daemon status (no pid yet)
    res = run_cli(["daemon", "status", "TestValley"])
    assert res.returncode == 0
    assert "Daemon status:" in res.stdout

    # Onboard creates config and manifest
    with monkeypatch.context() as m:
        m.chdir(tmp_path)
        res2 = run_cli(["onboard", "MyValley"])
        assert res2.returncode == 0
        assert (tmp_path / "config").exists()
        assert (tmp_path / "manifest.yaml").exists()
        assert (tmp_path / ".secrets").exists()

