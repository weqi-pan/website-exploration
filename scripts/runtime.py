from __future__ import annotations
import argparse, asyncio, json, os, sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

SCRIPTS_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(PACKAGE_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
import skillenv

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(skillenv.BROWSERS_DIR))
if skillenv.reexec_in_venv([str(Path(__file__).resolve()), *sys.argv[1:]]):
    sys.exit(0)

from scripts.browser import BrowserSession
from scripts.config import ExplorationConfig
from scripts.reporting import create_run_paths, build_fallback_report, append_screenshot_index, write_report
from scripts.evidence import EvidenceStore
from scripts.funclist import generate_descriptions
from scripts.docx_export import export_function_list_docx
from scripts.navigation import detect_navigation
from scripts.login import perform_login
from runtime.models import RuntimeSession

sessions: dict[str, RuntimeSession] = {}

async def dispatch(request: dict) -> dict:
    method, p = request.get("method"), request.get("params") or {}
    if method == "open_website":
        if not p.get("scope") and not p.get("target"):
            raise ValueError("open_website 必须明确指定探索范围 --scope 或探索目标 --target")
        output = Path(p["output_dir"]).expanduser().resolve()
        paths = create_run_paths(p["url"], output)
        config = ExplorationConfig.from_json(p["config_path"]) if p.get("config_path") else ExplorationConfig()
        max_pages = p.get("max_pages")
        max_actions = p.get("max_actions")
        browser = BrowserSession(headed=bool(p.get("headed")), max_pages=int(max_pages) if max_pages is not None else None, max_actions=int(max_actions) if max_actions is not None else None, screenshot_dir=paths.screenshot_dir, screenshot_relative_dir=paths.screenshot_relative_dir, allow_form_submit=bool(p.get("allow_form_submit", False)), blocked_keywords=config.blocked_action_keywords)
        await browser.__aenter__()
        sid = uuid4().hex
        targets = [str(item) for item in (p.get("target") or [])]
        sessions[sid] = RuntimeSession(browser, paths, config, p["url"], p.get("system_name") or p["url"], p.get("scope"), targets)
        result = await browser.open_url(p["url"])
        if config.has_login:
            result["login"] = (await perform_login(browser.page, config)).to_dict()
        (paths.run_dir / "session.json").write_text(json.dumps({"sessionId": sid, "outputDir": str(paths.run_dir), "url": p["url"], "scope": p.get("scope"), "target": p.get("target"), "limits": {"maxPages": max_pages, "maxActions": max_actions}}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {**result, "sessionId": sid, "outputDir": str(paths.run_dir)}
    sid = p.get("session_id")
    runtime = sessions.get(sid)
    if runtime is None: raise ValueError("未知或已关闭的 session_id")
    b = runtime.browser
    if method == "observe_page": return await b.observe()
    if method == "click_element": return await b.click_element(int(p["element_id"]))
    if method == "fill_element": return await b.fill_element(int(p["element_id"]), p["value"])
    if method == "inspect_form":
        snapshot = await b.observe()
        return {"forms": [item for item in snapshot.get("elements", []) if item.get("kind") == "form"]}
    if method == "login":
        return (await perform_login(b.page, runtime.config)).to_dict()
    if method == "submit_form": return await b.fill_and_submit_form(int(p["form_id"]))
    if method == "visit_url": return await b.visit_url(p["url"])
    if method == "go_back": return await b.go_back()
    if method == "return_to_base": return await b.return_to_base()
    if method == "get_navigation_map":
        nav = await detect_navigation(b.page, runtime.config); b.navigation_map = nav; b.set_base_url(nav.base_url); return nav.to_dict()
    if method == "get_exploration_log": return {"events": b.get_log(), "outputDir": str(runtime.paths.run_dir)}
    if method == "take_screenshot":
        name = str(p.get("name") or "page").replace("/", "-").replace("\\", "-")
        path = runtime.paths.screenshot_dir / f"manual-{name}.png"; await b.page.screenshot(path=path, full_page=True); return {"ok": True, "path": str(path)}
    if method == "finish_exploration":
        events = b.get_log()
        store = EvidenceStore(system_name=runtime.system_name, start_url=runtime.url, run_id=runtime.paths.run_id, account_label="", nav_map=b.navigation_map, environment=b.environment, limits={"maxPages": b.max_pages, "maxActions": b.max_actions}, started_at=events[0].get("time", "") if events else "", scope=runtime.scope, target=runtime.target)
        store.ingest(events, b.observe_snapshots); pages = store.build_pages(); await generate_descriptions(pages, model=None)
        data = store.to_dict(datetime.now().isoformat(timespec="seconds"), pages=pages)
        runtime.paths.pages_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(runtime.paths.report_path, append_screenshot_index(build_fallback_report(runtime.url, events, scope=runtime.scope, target=runtime.target), events))
        docx = None
        try: docx = export_function_list_docx(pages, runtime.system_name, runtime.paths.docx_path, assets_base=runtime.paths.run_dir)
        except Exception: pass
        (runtime.paths.run_dir / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "outputDir": str(runtime.paths.run_dir), "reportPath": str(runtime.paths.report_path), "pagesPath": str(runtime.paths.pages_path), "docxPath": str(docx) if docx else None, "coverage": data["meta"]["coverage"]}
    if method == "session_status": return {"sessionId": sid, "url": b.page.url if b.page else None, "actions": b.action_count, "visitedPages": len(b.visited_urls)}
    if method == "close_session": await b.__aexit__(None, None, None); sessions.pop(sid, None); return {"ok": True}
    raise ValueError(f"未知工具: {method}")

async def client(reader, writer):
    async for line in reader:
        try: response = {"ok": True, "result": await dispatch(json.loads(line))}
        except Exception as exc: response = {"ok": False, "error": str(exc)}
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode()); await writer.drain()

async def main():
    p = argparse.ArgumentParser(); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=38761); a = p.parse_args()
    server = await asyncio.start_server(client, a.host, a.port); print(json.dumps({"ok": True, "port": a.port}), flush=True)
    async with server: await server.serve_forever()
if __name__ == "__main__": asyncio.run(main())
