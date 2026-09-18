from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import Page

from .config import ExplorationConfig

DEFAULT_SELECTORS: dict[str, tuple[str, ...]] = {
    "sidebar": (
        ".el-menu-item", ".el-submenu__title", ".ant-menu-item",
        ".ant-menu-submenu-title", ".layui-nav a", ".sidebar-menu a",
        ".nav-item a", "#sidebar a", "aside li a", "[role='menuitem']",
    ),
    "cards": (
        ".dashboard-card", ".shortcut-item", ".dashboard-item",
        ".card", "a[class*='card']", "[class*='card'][onclick]",
    ),
    "tabs": (
        "[role='tab']", ".el-tabs__item", ".ant-tabs-tab",
        ".nav-tabs li a", "ul.tabs li",
    ),
}
NAV_ITEM_THRESHOLD = {"sidebar": 3, "cards": 4, "tabs": 2}
MODE_PRIORITY = ("sidebar", "cards", "tabs")


@dataclass
class NavItem:
    nav_id: int
    text: str
    href: str | None
    kind: str


@dataclass
class NavigationMap:
    mode: str
    items: list[NavItem] = field(default_factory=list)
    base_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "baseUrl": self.base_url,
            "items": [
                {"navId": i.nav_id, "text": i.text, "href": i.href, "kind": i.kind}
                for i in self.items
            ],
        }


async def _collect_items(
    page: Page, kind: str, configured: str
) -> list[tuple[str, str | None]]:
    selectors = tuple(
        s.strip() for s in configured.split(",") if s.strip()
    ) or DEFAULT_SELECTORS[kind]
    found: list[tuple[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
        except Exception:
            continue
        for index in range(min(count, 30)):
            node = locator.nth(index)
            try:
                if not await node.is_visible():
                    continue
                text = (await node.inner_text(timeout=300)).strip()
                if not text:
                    text = (
                        await node.get_attribute("aria-label")
                        or await node.get_attribute("title")
                        or ""
                    ).strip()
                if not text or len(text) > 40:
                    continue
                href = await node.get_attribute("href")
                if href:
                    href = urljoin(page.url, href)
                key = (text, href)
                if key in seen:
                    continue
                seen.add(key)
                found.append(key)
            except Exception:
                continue
        if len(found) >= 50:
            break
    return found[:50]


async def detect_navigation(page: Page, config: ExplorationConfig) -> NavigationMap:
    base_url = page.url
    if config.nav_mode in {"none", ""}:
        return NavigationMap("none", [], base_url)

    explicit = config.nav_mode if config.nav_mode in DEFAULT_SELECTORS else None
    configured_map = {
        "sidebar": config.nav_selectors.menu_items,
        "cards": config.nav_selectors.cards,
        "tabs": config.nav_selectors.tabs,
    }
    candidates: dict[str, list[tuple[str, str | None]]] = {}
    for mode in MODE_PRIORITY:
        if explicit and mode != explicit:
            continue
        candidates[mode] = await _collect_items(page, mode, configured_map[mode])

    chosen: str | None = None
    if explicit:
        chosen = explicit
    else:
        best_count = 0
        for mode in MODE_PRIORITY:
            count = len(candidates.get(mode, []))
            if count >= NAV_ITEM_THRESHOLD[mode] and count > best_count:
                best_count = count
                chosen = mode

    if not chosen or len(candidates.get(chosen, [])) < NAV_ITEM_THRESHOLD.get(chosen, 1):
        return NavigationMap("none", [], base_url)

    items = [
        NavItem(index + 1, text, href, chosen)
        for index, (text, href) in enumerate(candidates[chosen])
    ]
    return NavigationMap(chosen, items, base_url)
