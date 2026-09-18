from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import re
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from playwright.async_api import Browser, BrowserContext, Locator, Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from .safety import safe_text, safe_value


TEST_VALUES = {
    "email": "agent-demo@example.com",
    "tel": "13800138000",
    "url": "https://example.com",
    "number": "1",
    "date": "2026-08-03",
    "default": "智能体自动测试",
}

DEFAULT_BLOCKED_KEYWORDS = (
    "删除", "移除", "注销", "停用", "禁用", "清空", "重置", "卸载",
    "支付", "扣款", "退款", "提交审批", "发布上线", "批量操作", "导出全部",
)


class BrowserSession:
    def __init__(
        self,
        headed: bool = False,
        max_pages: int | None = None,
        max_actions: int | None = None,
        *,
        screenshot_dir: Path | None = None,
        screenshot_relative_dir: Path | None = None,
        allow_form_submit: bool = False,
        blocked_keywords: tuple[str, ...] = (),
    ):
        self.headed = headed
        self.max_pages = max_pages
        self.max_actions = max_actions
        self.action_count = 0
        self.visited_urls: set[str] = set()
        self.events: list[dict[str, Any]] = []
        self.start_origin: str | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self._elements: dict[int, Locator] = {}
        self._new_pages: asyncio.Queue[Page] = asyncio.Queue()
        self.screenshot_dir = screenshot_dir
        self.screenshot_relative_dir = screenshot_relative_dir
        self._screenshot_counter = 0
        self._screenshot_urls: set[str] = set()
        self.allow_form_submit = allow_form_submit
        self.blocked_keywords = DEFAULT_BLOCKED_KEYWORDS + tuple(blocked_keywords)
        self.environment: dict[str, Any] = {}
        self.observe_snapshots: dict[str, dict[str, Any]] = {}
        self.base_url: str | None = None
        self.navigation_map = None
        if self.screenshot_dir:
            try:
                self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                failed_dir = self.screenshot_dir
                self.screenshot_dir = None
                self._record(
                    "screenshot",
                    "截图目录",
                    {
                        "ok": False,
                        "kind": "setup",
                        "path": str(failed_dir),
                        "error": f"截图目录不可用，已禁用截图：{exc}",
                    },
                )

    async def __aenter__(self) -> "BrowserSession":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=not self.headed)
        self.context = await self._browser.new_context()
        self.page = await self.context.new_page()
        self.context.on("page", self._on_new_page)
        self._bind_page(self.page)
        try:
            user_agent = await self.page.evaluate("() => navigator.userAgent")
        except Exception:
            user_agent = ""
        viewport = self.page.viewport_size or {}
        self.environment = {
            "browser": f"chromium {self._browser.version}",
            "userAgent": user_agent,
            "viewport": f"{viewport.get('width', '?')}x{viewport.get('height', '?')}",
        }
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.context:
            await self.context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    def _bind_page(self, page: Page) -> None:
        page.on("dialog", lambda dialog: asyncio.create_task(self._handle_dialog(dialog)))

    def _on_new_page(self, page: Page) -> None:
        self._new_pages.put_nowait(page)

    async def _handle_dialog(self, dialog) -> None:
        self._record("dialog", dialog.type, f"弹窗内容：{dialog.message}")
        try:
            await dialog.accept()
        except Exception as exc:
            self._record("dialog_error", dialog.type, str(exc))

    def _record(self, action: str, target: str, result: Any) -> dict[str, Any]:
        event = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "target": safe_text(target),
            "result": safe_value(result),
            "url": safe_text(self.page.url) if self.page else "",
        }
        self.events.append(event)
        return event

    def _ensure_action_budget(self) -> None:
        if self.max_actions is not None and self.action_count >= self.max_actions:
            raise RuntimeError(f"已达到最大动作数 {self.max_actions}")
        self.action_count += 1

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parsed.port
        default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        port_suffix = f":{port}" if port and not default_port else ""
        return f"{scheme}://{hostname}{port_suffix}"

    def _same_origin(self, url: str) -> bool:
        return self.start_origin is None or self._origin(url) == self.start_origin

    async def _settle(self) -> None:
        if not self.page:
            return
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        await self.page.wait_for_timeout(250)

    @staticmethod
    def _safe_screenshot_slug(value: str) -> str:
        slug = re.sub(r"[^\w.-]+", "-", value.strip(), flags=re.UNICODE).strip("-._")
        return slug[:60] or "untitled"

    def _screenshot_name(self, kind: str, label: str) -> tuple[Path, str]:
        if not self.screenshot_dir:
            raise RuntimeError("未配置截图目录")
        self._screenshot_counter += 1
        filename = (
            f"{self._screenshot_counter:03d}-{kind}-"
            f"{self._safe_screenshot_slug(label)}.png"
        )
        output_path = self.screenshot_dir / filename
        relative_dir = self.screenshot_relative_dir or Path(self.screenshot_dir.name)
        return output_path, (relative_dir / filename).as_posix()

    async def _capture_new_page(self, label: str) -> None:
        if not self.page or not self.screenshot_dir:
            return
        normalized_url = urldefrag(self.page.url).url
        if normalized_url in self._screenshot_urls:
            return
        output_path, markdown_path = self._screenshot_name("page", label)
        try:
            await self.page.screenshot(path=output_path, full_page=True)
            result = {
                "ok": True,
                "kind": "page",
                "path": markdown_path,
                "url": self.page.url,
                "title": await self.page.title(),
                "label": label,
            }
            self._screenshot_urls.add(normalized_url)
        except Exception as exc:
            result = {
                "ok": False,
                "kind": "page",
                "url": self.page.url,
                "label": label,
                "error": str(exc),
            }
        self._record("screenshot", label, result)

    async def _capture_click_area(
        self, locator: Locator, label: str, element_id: int
    ) -> None:
        if not self.page or not self.screenshot_dir:
            return
        screenshot_label = label or f"element-{element_id}"
        output_path, markdown_path = self._screenshot_name("click", screenshot_label)
        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
            metrics = await locator.evaluate(
                """node => {
                    const rect = node.getBoundingClientRect();
                    const doc = document.documentElement;
                    const body = document.body;
                    return {
                        x: rect.left + window.scrollX,
                        y: rect.top + window.scrollY,
                        width: rect.width,
                        height: rect.height,
                        pageWidth: Math.max(doc.scrollWidth, body ? body.scrollWidth : 0),
                        pageHeight: Math.max(doc.scrollHeight, body ? body.scrollHeight : 0)
                    };
                }"""
            )
            padding = 120
            x = max(0, float(metrics["x"]) - padding)
            y = max(0, float(metrics["y"]) - padding)
            right = min(
                float(metrics["pageWidth"]),
                float(metrics["x"]) + float(metrics["width"]) + padding,
            )
            bottom = min(
                float(metrics["pageHeight"]),
                float(metrics["y"]) + float(metrics["height"]) + padding,
            )
            if right <= x or bottom <= y:
                raise ValueError("无法计算有效的按钮截图区域")
            try:
                await self.page.screenshot(
                    path=output_path,
                    clip={"x": x, "y": y, "width": right - x, "height": bottom - y},
                )
            except Exception:
                await locator.screenshot(path=output_path)
            result = {
                "ok": True,
                "kind": "click",
                "path": markdown_path,
                "url": self.page.url,
                "title": await self.page.title(),
                "label": screenshot_label,
                "element_id": element_id,
            }
        except Exception as exc:
            result = {
                "ok": False,
                "kind": "click",
                "url": self.page.url,
                "label": screenshot_label,
                "element_id": element_id,
                "error": str(exc),
            }
        self._record("screenshot", screenshot_label, result)

    async def open_url(self, url: str) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        self._ensure_action_budget()
        initial_open = self.start_origin is None
        if not initial_open and not self._same_origin(url):
            result = {"ok": False, "error": "拒绝主动访问非同域 URL", "url": url}
            self._record("open", url, result["error"])
            return result
        if self.max_pages is not None and url not in self.visited_urls and len(self.visited_urls) >= self.max_pages:
            result = {"ok": False, "error": f"已达到最大页面数 {self.max_pages}", "url": url}
            self._record("open", url, result["error"])
            return result
        try:
            previous_url = self.page.url
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await self._settle()
            if initial_open:
                self.start_origin = self._origin(self.page.url)
            elif not self._same_origin(self.page.url):
                redirected_url = self.page.url
                await self.page.goto(previous_url, wait_until="domcontentloaded", timeout=5000)
                result = {
                    "ok": False,
                    "url": redirected_url,
                    "error": "导航重定向到了非同域页面，已返回",
                }
                self._record("open", url, result)
                return result
            self.visited_urls.add(self.page.url)
            self._elements.clear()
            result = {
                "ok": True,
                "url": self.page.url,
                "title": await self.page.title(),
                "status": response.status if response else None,
            }
            self._record("open", url, result)
            await self._capture_new_page(result["title"] or "page")
            return result
        except Exception as exc:
            result = {"ok": False, "url": url, "error": str(exc)}
            self._record("open", url, result)
            return result

    async def observe(self) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        if self._same_origin(self.page.url):
            await self._capture_new_page(await self.page.title() or "page")
        self.visited_urls.add(self.page.url)
        self._elements = {}
        body_text = ""
        try:
            body_text = (await self.page.locator("body").inner_text(timeout=3000)).strip()
        except Exception:
            pass

        elements: list[dict[str, Any]] = []
        candidates = self.page.locator(
            "a, button, input, textarea, select, [role='button'], form"
        )
        count = await candidates.count()
        for index in range(count):
            if len(elements) >= 100:
                break
            locator = candidates.nth(index)
            try:
                if not await locator.is_visible():
                    continue
                tag = await locator.evaluate("node => node.tagName.toLowerCase()")
                input_type = (await locator.get_attribute("type") or "").lower()
                if tag == "a":
                    kind = "link"
                elif tag == "form":
                    kind = "form"
                elif tag == "button" or input_type in {"button", "submit", "reset"}:
                    kind = "button"
                else:
                    kind = "input"
                try:
                    text = (await locator.inner_text(timeout=500)).strip()
                except Exception:
                    text = ""
                if not text:
                    text = (
                        await locator.get_attribute("aria-label")
                        or await locator.get_attribute("placeholder")
                        or await locator.get_attribute("name")
                        or input_type
                        or tag
                    )
                element_id = len(self._elements) + 1
                self._elements[element_id] = locator
                item: dict[str, Any] = {
                    "id": element_id,
                    "kind": kind,
                    "tag": tag,
                    "text": text[:300],
                }
                if tag == "a":
                    href = await locator.get_attribute("href")
                    item["href"] = urljoin(self.page.url, href) if href else None
                elif tag == "form":
                    action = await locator.get_attribute("action")
                    item["action"] = urljoin(self.page.url, action) if action else self.page.url
                else:
                    item["name"] = await locator.get_attribute("name")
                    item["type"] = input_type or tag
                elements.append(item)
            except Exception:
                continue

        try:
            has_table = await self.page.locator("table").count() > 0
        except Exception:
            has_table = False
        has_form = any(item["kind"] == "form" for item in elements)
        snapshot = {
            "url": self.page.url,
            "title": await self.page.title(),
            "text": body_text[:4000],
            "elements": elements,
            "hasTable": has_table,
            "hasForm": has_form,
            "pages_visited": len(self.visited_urls),
            "actions_used": self.action_count,
            "limits": {"max_pages": self.max_pages, "max_actions": self.max_actions},
        }
        self.observe_snapshots[urldefrag(self.page.url).url] = {
            "title": snapshot["title"],
            "text": body_text,
            "elements": elements,
            "hasTable": has_table,
            "hasForm": has_form,
        }
        self._record("observe", self.page.url, f"发现 {len(elements)} 个可操作元素")
        return snapshot

    def _element(self, element_id: int) -> Locator:
        try:
            return self._elements[element_id]
        except KeyError as exc:
            raise ValueError(f"元素 ID {element_id} 不存在，请重新观察页面") from exc

    async def _body_text(self) -> str:
        if not self.page:
            return ""
        try:
            return (await self.page.locator("body").inner_text(timeout=3000)).strip()[:4000]
        except Exception:
            return ""

    async def _adopt_new_page(self, previous_pages: set[Page], timeout: float) -> bool:
        if not self.context:
            return False
        while not self._new_pages.empty():
            self._new_pages.get_nowait()
        try:
            new_page = await asyncio.wait_for(self._new_pages.get(), timeout=timeout)
        except TimeoutError:
            new_page = None
        new_pages = [page for page in self.context.pages if page not in previous_pages]
        if new_page and new_page not in new_pages:
            new_pages.append(new_page)
        if not new_pages:
            return False
        self.page = new_pages[-1]
        self._bind_page(self.page)
        await self._settle()
        self._record("new_page", self.page.url, "点击操作打开了新页面，已切换")
        return True

    async def _enforce_navigation_bounds(
        self, previous_page: Page, safe_url: str
    ) -> str | None:
        if not self.page:
            return None
        if not self._same_origin(self.page.url):
            outside_url = self.page.url
            if self.page is not previous_page:
                await self.page.close()
                self.page = previous_page
            else:
                await self.page.goto(safe_url, wait_until="domcontentloaded", timeout=5000)
            await self._settle()
            return f"操作打开了非同域页面 {outside_url}，已返回"
        if self.page.url not in self.visited_urls:
            if self.max_pages is not None and len(self.visited_urls) >= self.max_pages:
                overflow_url = self.page.url
                if self.page is not previous_page:
                    await self.page.close()
                    self.page = previous_page
                else:
                    await self.page.goto(safe_url, wait_until="domcontentloaded", timeout=5000)
                await self._settle()
                return f"新页面 {overflow_url} 超出页面数量上限，已返回"
            self.visited_urls.add(self.page.url)
        return None

    def _blocked_reason(self, text: str) -> str | None:
        for keyword in self.blocked_keywords:
            if keyword and keyword in text:
                return f"命中安全清单关键词：{keyword}"
        return None

    async def click_element(self, element_id: int) -> dict[str, Any]:
        if not self.page or not self.context:
            raise RuntimeError("浏览器尚未启动")
        self._ensure_action_budget()
        try:
            locator = self._element(element_id)
        except ValueError as exc:
            result = {"ok": False, "target": f"元素 {element_id}", "error": str(exc)}
            self._record("click", f"元素 {element_id}", result)
            return result
        previous_page = self.page
        previous_pages = set(self.context.pages)
        before_url = self.page.url
        before_title = await self.page.title()
        before_text = await self._body_text()
        try:
            target = (await locator.inner_text(timeout=500)).strip() or f"元素 {element_id}"
        except Exception:
            target = f"元素 {element_id}"
        reason = self._blocked_reason(target)
        if reason:
            result = {
                "ok": False,
                "blocked": True,
                "target": target,
                "text": target,
                "reason": reason,
                "url": self.page.url,
            }
            self._record("blocked_click", target, result)
            return result
        try:
            target_attr = (await locator.get_attribute("target") or "").lower()
            onclick = (await locator.get_attribute("onclick") or "").lower()
            popup_timeout = 1.2 if target_attr == "_blank" or "window.open" in onclick else 0.15
            await self._capture_click_area(locator, target, element_id)
            await locator.click(timeout=5000)
            await self._adopt_new_page(previous_pages, popup_timeout)
            await self._settle()
            boundary_note = await self._enforce_navigation_bounds(previous_page, before_url)
            after_text = await self._body_text()
            result = {
                "ok": True,
                "target": target,
                "before_url": before_url,
                "after_url": self.page.url if self.page else before_url,
                "before_title": before_title,
                "after_title": await self.page.title() if self.page else before_title,
                "before_text": before_text[:1200],
                "after_text": after_text[:1200],
                "note": boundary_note,
            }
            self._record("click", target, result)
            await self._capture_new_page(result["after_title"] or "page")
            self._elements.clear()
            return result
        except Exception as exc:
            result = {"ok": False, "target": target, "error": str(exc), "after_url": self.page.url}
            self._record("click", target, result)
            self._elements.clear()
            return result

    async def fill_element(self, element_id: int, value: str) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        self._ensure_action_budget()
        try:
            locator = self._element(element_id)
        except ValueError as exc:
            result = {"ok": False, "target": f"元素 {element_id}", "error": str(exc)}
            self._record("fill", f"元素 {element_id}", result)
            return result
        name = await locator.get_attribute("name") or f"元素 {element_id}"
        try:
            await locator.fill(value, timeout=3000)
            result = {"ok": True, "target": name, "value_length": len(value)}
            self._record("fill", name, result)
            return result
        except Exception as exc:
            result = {"ok": False, "target": name, "error": str(exc)}
            self._record("fill", name, result)
            return result

    async def fill_and_submit_form(self, form_id: int) -> dict[str, Any]:
        if not self.page or not self.context:
            raise RuntimeError("浏览器尚未启动")
        self._ensure_action_budget()
        try:
            form = self._element(form_id)
        except ValueError as exc:
            result = {"ok": False, "target": f"表单 {form_id}", "error": str(exc)}
            self._record("submit_form", f"表单 {form_id}", result)
            return result
        previous_page = self.page
        previous_pages = set(self.context.pages)
        before_url = self.page.url
        before_title = await self.page.title()
        filled_fields: list[str] = []
        try:
            fields = form.locator("input, textarea, select")
            for index in range(await fields.count()):
                field = fields.nth(index)
                if not await field.is_visible() or await field.is_disabled():
                    continue
                tag = await field.evaluate("node => node.tagName.toLowerCase()")
                input_type = (await field.get_attribute("type") or "text").lower()
                name = await field.get_attribute("name") or f"field-{index + 1}"
                if input_type in {"hidden", "submit", "reset", "button", "file", "image"}:
                    continue
                if input_type in {"checkbox", "radio"}:
                    if not await field.is_checked():
                        await field.check(timeout=3000)
                elif tag == "select":
                    options = field.locator("option:not([disabled])")
                    selected = False
                    for option_index in range(await options.count()):
                        option = options.nth(option_index)
                        option_value = await option.get_attribute("value")
                        if option_value:
                            await field.select_option(value=option_value)
                            selected = True
                            break
                    if not selected:
                        continue
                else:
                    value = TEST_VALUES.get(input_type, TEST_VALUES["default"])
                    await field.fill(value, timeout=3000)
                filled_fields.append(name)

            form_target = (await form.get_attribute("target") or "").lower()
            submit = form.locator("button[type='submit'], input[type='submit'], button:not([type])").first
            submit_label = ""
            try:
                submit_label = (await submit.inner_text(timeout=500)).strip() or "submit"
            except Exception:
                submit_label = "submit"
            blocked_reason = self._blocked_reason(submit_label)
            if blocked_reason or not self.allow_form_submit:
                note = (
                    blocked_reason
                    if blocked_reason
                    else "表单提交已被配置禁用，仅填写未提交"
                )
                after_text = await self._body_text()
                result = {
                    "ok": True,
                    "submitted": False,
                    "before_url": before_url,
                    "after_url": self.page.url,
                    "before_title": before_title,
                    "after_title": await self.page.title(),
                    "after_text": after_text[:1200],
                    "filled_fields": filled_fields,
                    "note": note,
                }
                action = "blocked_click" if blocked_reason else "submit_form"
                self._record(action, ", ".join(filled_fields) or f"表单 {form_id}", result)
                return result
            if await submit.count() and await submit.is_visible():
                await self._capture_click_area(submit, submit_label, form_id)
                await submit.click(timeout=5000)
            else:
                await form.evaluate("node => node.requestSubmit()")
            await self._adopt_new_page(previous_pages, 1.2 if form_target == "_blank" else 0.15)
            await self._settle()
            boundary_note = await self._enforce_navigation_bounds(previous_page, before_url)
            after_text = await self._body_text()
            result = {
                "ok": True,
                "submitted": True,
                "before_url": before_url,
                "after_url": self.page.url if self.page else before_url,
                "before_title": before_title,
                "after_title": await self.page.title() if self.page else before_title,
                "after_text": after_text[:1200],
                "filled_fields": filled_fields,
                "note": boundary_note,
            }
            self._record("submit_form", ", ".join(filled_fields) or f"表单 {form_id}", result)
            await self._capture_new_page(result["after_title"] or "page")
            self._elements.clear()
            return result
        except Exception as exc:
            result = {
                "ok": False,
                "before_url": before_url,
                "after_url": self.page.url,
                "filled_fields": filled_fields,
                "error": str(exc),
            }
            self._record("submit_form", f"表单 {form_id}", result)
            self._elements.clear()
            return result

    async def visit_url(self, url: str) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        return await self.open_url(urljoin(self.page.url, url))

    def set_base_url(self, url: str) -> None:
        self.base_url = url

    async def return_to_base(self) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        if not self.base_url:
            return {"ok": False, "error": "未设置基准页"}
        return await self.open_url(self.base_url)

    async def go_back(self) -> dict[str, Any]:
        if not self.page:
            raise RuntimeError("浏览器尚未启动")
        self._ensure_action_budget()
        before_url = self.page.url
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=5000)
            await self._settle()
            boundary_note = await self._enforce_navigation_bounds(self.page, before_url)
            if boundary_note:
                result = {
                    "ok": False,
                    "before_url": before_url,
                    "after_url": self.page.url,
                    "error": boundary_note,
                }
                self._record("back", before_url, result)
                return result
            self.visited_urls.add(self.page.url)
            self._elements.clear()
            result = {"ok": True, "before_url": before_url, "after_url": self.page.url}
            self._record("back", before_url, result)
            await self._capture_new_page(await self.page.title() or "page")
            return result
        except Exception as exc:
            result = {"ok": False, "before_url": before_url, "error": str(exc)}
            self._record("back", before_url, result)
            return result

    def get_log(self) -> list[dict[str, Any]]:
        return list(self.events)
