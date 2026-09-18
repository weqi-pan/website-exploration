from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag

from .navigation import NavigationMap


def _norm(url: str) -> str:
    return urldefrag(url or "").url


class EvidenceStore:
    def __init__(
        self,
        *,
        system_name: str,
        start_url: str,
        run_id: str,
        account_label: str,
        nav_map: NavigationMap | None,
        environment: dict,
        limits: dict,
        started_at: str,
        scope: str | None = None,
        target: list[str] | None = None,
    ):
        self.system_name = system_name
        self.start_url = start_url
        self.run_id = run_id
        self.account_label = account_label
        self.nav_map = nav_map
        self.environment = environment
        self.limits = limits
        self.started_at = started_at
        self.scope = scope
        self.target = target or []
        self._pages: dict[str, dict[str, Any]] = {}
        self._click_history: list[str] = []
        self._blocked: list[dict[str, Any]] = []
        self._clicked_texts: set[str] = set()

    # -- ingestion ---------------------------------------------------
    def ingest(self, events: list[dict], observe_snapshots: dict) -> None:
        for event in events:
            action = event.get("action")
            result = event.get("result")
            if not isinstance(result, dict):
                continue
            if action == "open" and result.get("ok"):
                self._register_page(
                    result.get("url", ""), result.get("title", ""), event.get("time", "")
                )
            elif action == "screenshot" and result.get("ok") and result.get("kind") == "page":
                page = self._pages.get(_norm(result.get("url", "")))
                if page is not None and not page.get("screenshot"):
                    page["screenshot"] = result.get("path")
            elif action == "click" and result.get("ok"):
                target = str(result.get("target") or event.get("target") or "")
                if target:
                    self._click_history.append(target)
                    self._clicked_texts.add(target)
                before_url = _norm(result.get("before_url", ""))
                after_url = result.get("after_url", "")
                if after_url and _norm(after_url) != before_url:
                    self._register_page(
                        after_url,
                        result.get("after_title", ""),
                        event.get("time", ""),
                    )
            elif action == "blocked_click":
                self._blocked.append(
                    {
                        "time": event.get("time", ""),
                        "text": result.get("text") or event.get("target", ""),
                        "url": result.get("url", ""),
                        "reason": result.get("reason", ""),
                    }
                )
        for url, snapshot in observe_snapshots.items():
            page = self._pages.get(_norm(url))
            if page is None:
                continue
            page["title"] = page["title"] or snapshot.get("title", "")
            elements = snapshot.get("elements", [])
            page["buttons"] = [
                e["text"] for e in elements if e.get("kind") == "button" and e.get("text")
            ][:20]
            page["hasTable"] = bool(snapshot.get("hasTable"))
            page["hasForm"] = bool(snapshot.get("hasForm"))
            page["contentDigest"] = (snapshot.get("text") or "").strip()[:600]

    def _register_page(self, url: str, title: str, time: str) -> None:
        key = _norm(url)
        if key in self._pages:
            return
        self._pages[key] = {
            "url": url,
            "title": title,
            "screenshot": None,
            "buttons": [],
            "hasTable": False,
            "hasForm": False,
            "contentDigest": "",
            "entryPath": list(self._click_history[-6:]) + ([title] if title else []),
            "firstSeenAt": time,
        }

    # -- derived -----------------------------------------------------
    def _match_nav(self, url: str) -> str:
        if not self.nav_map:
            return ""
        for item in self.nav_map.items:
            if item.href and _norm(url) == _norm(item.href):
                return item.text
        return ""

    def build_pages(self) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for index, page in enumerate(self._pages.values(), 1):
            nav_module = self._match_nav(page["url"])
            pages.append(
                {
                    "id": index,
                    "name": page["title"] or nav_module or f"页面{index}",
                    "moduleName": nav_module,
                    "url": page["url"],
                    "title": page["title"],
                    "entryPath": page["entryPath"],
                    "firstSeenAt": page["firstSeenAt"],
                    "screenshot": page["screenshot"],
                    "clickTrail": page["entryPath"][:-1],
                    "contentDigest": page["contentDigest"],
                    "buttons": page["buttons"],
                    "hasTable": page["hasTable"],
                    "hasForm": page["hasForm"],
                    "functionDescription": "",
                    "descriptionConfidence": None,
                    "remarks": "",
                }
            )
        return pages

    def coverage(self) -> dict:
        if not self.nav_map or not self.nav_map.items:
            return {"navItemsTotal": 0, "navItemsVisited": 0, "ratio": None}
        visited_urls = set(self._pages.keys())
        visited = 0
        for item in self.nav_map.items:
            if (item.href and _norm(item.href) in visited_urls) or (
                item.text in self._clicked_texts
            ):
                visited += 1
        total = len(self.nav_map.items)
        return {
            "navItemsTotal": total,
            "navItemsVisited": visited,
            "ratio": round(visited / total, 4) if total else None,
        }

    def to_dict(
        self, finished_at: str, pages: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "meta": {
                "systemName": self.system_name,
                "startUrl": self.start_url,
                "runId": self.run_id,
                "startedAt": self.started_at,
                "finishedAt": finished_at,
                "controlledAccount": self.account_label,
                "navigationMode": self.nav_map.mode if self.nav_map else "none",
                "environment": self.environment,
                "coverage": self.coverage(),
                "limits": self.limits,
                "scope": self.scope,
                "target": self.target,
                "blockedActions": list(self._blocked),
            },
            "pages": pages if pages is not None else self.build_pages(),
        }
