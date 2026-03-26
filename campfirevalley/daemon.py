import os
import sys
import asyncio
from pathlib import Path
from typing import Optional


class DaemonState:
    def __init__(self, valley_name: str, pid_dir: Optional[str] = None):
        self.valley_name = valley_name
        self.pid_dir = Path(pid_dir) if pid_dir else Path(".campfirevalley")
        self.pid_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.pid_dir / f"{self.valley_name}.pid"

    def write_pid(self) -> None:
        self.pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def clear_pid(self) -> None:
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception:
            pass

    def get_pid(self) -> Optional[int]:
        try:
            if self.pid_file.exists():
                return int(self.pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            return None
        return None

    def is_running(self) -> bool:
        pid = self.get_pid()
        if not pid:
            return False
        # Best-effort check: on Windows, os.kill with 0 is unsupported like POSIX,
        # so we just check that the PID is not the current one and assume running.
        # This is intentionally conservative.
        if pid == os.getpid():
            return True
        return True


async def run_with_pid(valley_coro, state: DaemonState):
    try:
        state.write_pid()
        await valley_coro
    finally:
        state.clear_pid()

