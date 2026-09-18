from __future__ import annotations
import json, socket, subprocess, sys, time
from pathlib import Path

HOST, PORT = "127.0.0.1", 38761
ROOT = Path(__file__).resolve().parent.parent

def ensure_runtime() -> None:
    try:
        with socket.create_connection((HOST, PORT), timeout=.3): return
    except OSError: pass
    subprocess.Popen([sys.executable, str(ROOT / "scripts" / "runtime.py"), "--host", HOST, "--port", str(PORT)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        try:
            with socket.create_connection((HOST, PORT), timeout=.3): return
        except OSError: time.sleep(.1)
    raise RuntimeError("无法启动 Browser Runtime")

def request(method: str, params: dict) -> dict:
    ensure_runtime()
    with socket.create_connection((HOST, PORT), timeout=120) as sock:
        sock.sendall((json.dumps({"method": method, "params": params}) + "\n").encode())
        return json.loads(sock.makefile("rb").readline())
