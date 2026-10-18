"""
Safe shutdown script for Dakota Financial Intelligence Platform.
Terminates ONLY the processes associated with:
  1. Dakota Backend (FastAPI on Port 8000)
  2. Dakota Frontend (Next.js dev server on Port 3000)
  3. Dakota Telegram Shell Builder (scripts/telegram/channel_reader.py)

Leaves all other system, Python, and Node.js processes untouched.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    import psutil
except ImportError:
    print("[WARN] psutil not installed in environment, falling back to basic shutdown.")
    psutil = None


def stop_process_by_port(port: int, expected_name: str, display_label: str) -> bool:
    """Find and terminate only the process listening on a specific port matching expected_name."""
    stopped = False
    if not psutil:
        return False

    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            pid = conn.pid
            if not pid or pid == os.getpid():
                continue
            try:
                proc = psutil.Process(pid)
                pname = proc.name().lower()
                if expected_name.lower() in pname:
                    print(f"  [*] Stopping {display_label} (PID {pid}, {proc.name()})...")
                    # Terminate children first (e.g. Next.js workers)
                    for child in proc.children(recursive=True):
                        try:
                            child.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    proc.kill()
                    stopped = True
                    print(f"  [OK] {display_label} stopped successfully.")
                else:
                    print(f"  [SKIP] Port {port} occupied by unrelated process '{proc.name()}' (PID {pid}). Left intact.")
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                print(f"  [!] Could not terminate PID {pid}: {exc}")
    return stopped


def stop_telegram_builder() -> bool:
    """Find and terminate only the Python process running channel_reader.py."""
    stopped = False
    if not psutil:
        return False

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            pid = proc.info["pid"]
            if pid == os.getpid():
                continue
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()
            if "channel_reader.py" in cmd_str:
                print(f"  [*] Stopping Telegram Shell Builder (PID {pid})...")
                proc.kill()
                stopped = True
                print(f"  [OK] Telegram Shell Builder (PID {pid}) stopped successfully.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return stopped


def main() -> None:
    print("=" * 68)
    print("           DAKOTA SYSTEM CONTROLLER - SAFE SHUTDOWN")
    print("=" * 68)
    print()

    # 1. Backend on Port 8000
    print("[1/3] Checking Dakota Backend (Port 8000)...")
    b_stopped = stop_process_by_port(8000, "python", "Dakota Backend")
    if not b_stopped:
        print("  [-] Dakota Backend was not running on port 8000.")
    print()

    # 2. Frontend on Port 3000
    print("[2/3] Checking Dakota Frontend (Port 3000)...")
    f_stopped = stop_process_by_port(3000, "node", "Dakota Frontend")
    if not f_stopped:
        print("  [-] Dakota Frontend was not running on port 3000.")
    print()

    # 3. Telegram Shell Builder
    print("[3/3] Checking Dakota Telegram Shell Builder...")
    t_stopped = stop_telegram_builder()
    if not t_stopped:
        print("  [-] Telegram Shell Builder was not running.")
    print()

    # 4. State file cleanup
    pid_file = ROOT / "logs" / "dakota_launcher.pid"
    if pid_file.exists():
        try:
            pid_file.unlink()
        except OSError:
            pass

    print("=" * 68)
    print("                 ALL DAKOTA SERVICES SAFELY STOPPED")
    print("=" * 68)


if __name__ == "__main__":
    main()
