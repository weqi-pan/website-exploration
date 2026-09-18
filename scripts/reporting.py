from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .safety import safe_text, safe_value


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    run_dir: Path
    report_path: Path
    pages_path: Path
    docx_path: Path
    screenshot_dir: Path
    screenshot_relative_dir: Path


def _safe_host(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", urlparse(url).netloc or "website")


def create_run_paths(url: str, output_dir: Path) -> RunPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{_safe_host(url)}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = run_dir / "assets"
    try:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        # 截图是附加能力；目录不可用时仍允许主报告继续生成。
        pass
    return RunPaths(
        run_id=run_id,
        run_dir=run_dir,
        report_path=run_dir / "report.md",
        pages_path=run_dir / "pages.json",
        docx_path=run_dir / f"{run_id}_功能清单.docx",
        screenshot_dir=screenshot_dir,
        screenshot_relative_dir=Path("assets"),
    )


def write_report(path: Path, markdown: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(safe_text(markdown).rstrip() + "\n", encoding="utf-8")
    return path


def save_report(url: str, markdown: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    host = _safe_host(url)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = output_dir / f"{host}-{stamp}.md"
    counter = 1
    while path.exists():
        path = output_dir / f"{host}-{stamp}-{counter}.md"
        counter += 1
    return write_report(path, markdown)


def append_screenshot_index(markdown: str, events: list[dict]) -> str:
    events = safe_value(events)
    screenshot_events = [event for event in events if event.get("action") == "screenshot"]
    lines = [markdown.rstrip(), "", "## 9. 截图索引", ""]
    if not screenshot_events:
        lines.append("本次探索未生成可用截图。")
        return "\n".join(lines)

    successful = 0
    for event in screenshot_events:
        result = event.get("result") or {}
        kind = result.get("kind", "page")
        label = str(result.get("label") or event.get("target") or "未命名")
        kind_label = "页面截图" if kind == "page" else "点击截图"
        lines.extend([f"### {kind_label}：{label}", ""])
        if result.get("url"):
            lines.extend([f"- URL：{result['url']}", ""])
        if result.get("ok") and result.get("path"):
            alt = f"{kind_label}：{label}".replace("]", "")
            lines.extend([f"![{alt}]({result['path']})", ""])
            successful += 1
        else:
            lines.extend([f"截图失败：{result.get('error', '未知错误')}", ""])

    if successful == 0:
        lines.append("本次探索没有成功生成可用截图。")
    return "\n".join(lines)


def build_fallback_report(url: str, events: list[dict], *, scope: str | None = None, target: list[str] | None = None) -> str:
    url = safe_text(url)
    events = safe_value(events)
    lines = [
        "# 网站功能探索报告",
        "",
        f"- 目标网站：{url}",
        f"- 探索范围：{scope or '未记录'}",
        f"- 探索目标：{'；'.join(target or []) or '未指定'}",
        "- 说明：以下内容根据浏览器实际操作日志自动整理。",
        "",
        "## 探索记录",
        "",
    ]
    if not events:
        lines.append("未获得有效操作记录。")
    for index, event in enumerate(events, 1):
        fallback = json.dumps(event, ensure_ascii=False)
        raw_result = event.get("result", fallback)
        rendered_result = (
            raw_result
            if isinstance(raw_result, str)
            else json.dumps(raw_result, ensure_ascii=False)
        )
        lines.extend(
            [
                f"### {index}. {event.get('action', 'observe')}",
                "",
                f"- 目标：{event.get('target', '-')}",
                f"- 结果：{rendered_result}",
                "",
            ]
        )
    return "\n".join(lines)
