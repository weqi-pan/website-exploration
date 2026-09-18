from __future__ import annotations
import argparse, json, socket, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import skillenv

HOST, PORT = "127.0.0.1", 38761

def ensure_runtime():
    try:
        with socket.create_connection((HOST, PORT), timeout=.3): return
    except OSError: pass
    python = skillenv.venv_python()
    if not python.exists():
        raise RuntimeError("未找到技能内置虚拟环境，请先运行: python scripts/bootstrap.py")
    subprocess.Popen([str(python), str(ROOT / "runtime.py"), "--host", HOST, "--port", str(PORT)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=skillenv.browser_env())
    for _ in range(30):
        try:
            with socket.create_connection((HOST, PORT), timeout=.3): return
        except OSError: time.sleep(.1)
    raise RuntimeError("无法启动 Browser Runtime")

def main():
    p = argparse.ArgumentParser(); p.add_argument("command"); p.add_argument("--session-id"); p.add_argument("--url"); p.add_argument("--output-dir"); p.add_argument("--config-path"); p.add_argument("--system-name"); p.add_argument("--element-id", type=int); p.add_argument("--form-id", type=int); p.add_argument("--value"); p.add_argument("--name"); p.add_argument("--headed", action="store_true"); p.add_argument("--scope", choices=["current", "section", "subtree", "site"]); p.add_argument("--target", action="append", help="探索目标路径，可重复传入，例如：板块A > 子板块A2"); p.add_argument("--max-pages", type=int); p.add_argument("--max-actions", type=int); p.add_argument("--allow-form-submit", action="store_true")
    a = p.parse_args()
    if a.command == "open_website" and (not a.url or not a.output_dir):
        p.error("open_website requires --url and --output-dir")
    if a.command == "open_website" and not a.scope and not a.target:
        p.error("open_website requires --scope or --target; 未明确探索范围时不会执行探索")
    if a.command != "open_website" and not a.session_id:
        p.error(f"{a.command} requires --session-id")
    ensure_runtime(); params = {"session_id": a.session_id, "url": a.url, "output_dir": a.output_dir, "config_path": a.config_path, "system_name": a.system_name, "element_id": a.element_id, "form_id": a.form_id, "value": a.value, "name": a.name, "headed": a.headed, "scope": a.scope, "target": a.target, "max_pages": a.max_pages, "max_actions": a.max_actions, "allow_form_submit": a.allow_form_submit}
    with socket.create_connection((HOST, PORT), timeout=120) as s:
        s.sendall((json.dumps({"method": a.command, "params": params}) + "\n").encode()); data = s.makefile("rb").readline()
    result = json.loads(data); print(json.dumps(result.get("result", result), ensure_ascii=False, indent=2)); raise SystemExit(0 if result.get("ok") else 1)
if __name__ == "__main__": main()
