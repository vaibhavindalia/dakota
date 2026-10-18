"""
Status check utility for Dakota Financial Intelligence Platform.
Checks availability of:
  - Port 8000 (Backend API)
  - Port 3000 (Frontend Web UI)
  - Telegram Shell Builder process (channel_reader.py)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    import psutil
except ImportError:
    psutil = None


def is_port_listening(port: int) -> tuple[bool, int | None, str | None]:
    if not psutil:
        return False, None, None
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            pid = conn.pid
            name = None
            if pid:
                try:
                    name = psutil.Process(pid).name()
                except Exception:
                    pass
            return True, pid, name
    return False, None, None


def is_telegram_running() -> tuple[bool, int | None]:
    if not psutil:
        return False, None
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            pid = proc.info["pid"]
            if pid == os.getpid():
                continue
            cmdline = proc.info.get("cmdline") or []
            if any("channel_reader.py" in arg for arg in cmdline):
                return True, pid
        except Exception:
            continue
    return False, None


def main() -> None:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else "summary"

    b_listen, b_pid, b_name = is_port_listening(8000)
    f_listen, f_pid, f_name = is_port_listening(3000)
    t_running, t_pid = is_telegram_running()

    if arg == "backend":
        sys.exit(0 if b_listen else 1)
    elif arg == "frontend":
        sys.exit(0 if f_listen else 1)
    elif arg == "telegram":
        sys.exit(0 if t_running else 1)
    elif arg == "summary":
        print(f"Backend  (8000): {'ONLINE (PID ' + str(b_pid) + ')' if b_listen else 'OFFLINE'}")
        print(f"Frontend (3000): {'ONLINE (PID ' + str(f_pid) + ')' if f_listen else 'OFFLINE'}")
        print(f"Telegram Stream: {'ACTIVE (PID ' + str(t_pid) + ')' if t_running else 'INACTIVE'}")


if __name__ == "__main__":
    main()
