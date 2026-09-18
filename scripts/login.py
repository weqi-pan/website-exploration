from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from playwright.async_api import Page

from .config import ExplorationConfig

DEFAULT_USERNAME_SELECTORS = (
    "input[name='username']", "input[name='user']", "input[name='account']",
    "input[placeholder*='账号']", "input[placeholder*='用户名']", "input[type='text']",
)
DEFAULT_PASSWORD_SELECTORS = (
    "input[name='password']", "input[type='password']",
)
DEFAULT_SUBMIT_SELECTORS = (
    "button[type='submit']", ".login-btn", ".el-button--primary",
    "input[type='submit']", "button:not([type])",
)
CAPTCHA_SELECTORS = (
    "img[src*='captcha']", "img[src*='verify']", "img[id*='captcha']",
    "[class*='captcha']", "[id*='captcha']", "[class*='verify-code']",
    ".geetest_box", "[class*='slide-verify']",
)
SUCCESS_HINT_SELECTORS = (
    "[class*='logout']", "a[href*='logout']", ".user-info", "[class*='user-name']",
)


@dataclass
class LoginResult:
    ok: bool
    status: str
    detail: str
    evidence: dict = field(default_factory=dict)


def mask_account(value: str) -> str:
    if len(value) <= 2:
        return "***"
    return f"{value[0]}***{value[-1]}"


def _configured_or_defaults(configured: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    if configured:
        parts = tuple(s.strip() for s in configured.split(",") if s.strip())
        return parts + defaults
    return defaults


async def _find_visible(page: Page, selectors: tuple[str, ...]):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible():
                return locator
        except Exception:
            continue
    return None


async def _save_shot(
    page: Page, screenshot_dir: Path | None, name: str, shots: list[str]
) -> None:
    if not screenshot_dir:
        return
    try:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = screenshot_dir / name
        await page.screenshot(path=path, full_page=True)
        shots.append(str(path))
    except Exception:
        pass


async def perform_login(
    page: Page, config: ExplorationConfig, screenshot_dir: Path | None = None
) -> LoginResult:
    shots: list[str] = []
    evidence = {
        "loginUrl": config.login_url,
        "account": mask_account(config.username),
        "time": datetime.now().isoformat(timespec="seconds"),
        "screenshots": shots,
    }
    await _save_shot(page, screenshot_dir, "login-before.png", shots)

    for selector in CAPTCHA_SELECTORS:
        try:
            if await page.locator(selector).count() > 0:
                return LoginResult(
                    False,
                    "needs_manual",
                    f"检测到疑似验证码元素（{selector}），请人工完成登录后使用受控会话重试",
                    evidence,
                )
        except Exception:
            continue

    user_box = await _find_visible(
        page,
        _configured_or_defaults(
            config.login_selectors.username_input, DEFAULT_USERNAME_SELECTORS
        ),
    )
    pass_box = await _find_visible(
        page,
        _configured_or_defaults(
            config.login_selectors.password_input, DEFAULT_PASSWORD_SELECTORS
        ),
    )
    if user_box is None or pass_box is None:
        return LoginResult(False, "failed", "未找到可见的账号或密码输入框", evidence)

    try:
        await user_box.fill(config.username, timeout=3000)
        await pass_box.fill(config.password, timeout=3000)
    except Exception as exc:
        return LoginResult(False, "failed", f"填写登录表单失败：{exc}", evidence)

    submit = await _find_visible(
        page,
        _configured_or_defaults(
            config.login_selectors.submit_button, DEFAULT_SUBMIT_SELECTORS
        ),
    )
    try:
        if submit is not None:
            await submit.click(timeout=5000)
        else:
            await pass_box.press("Enter")
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
        await page.wait_for_timeout(600)
    except Exception as exc:
        await _save_shot(page, screenshot_dir, "login-after.png", shots)
        return LoginResult(False, "failed", f"提交登录失败：{exc}", evidence)

    await _save_shot(page, screenshot_dir, "login-after.png", shots)
    logged_in = "login" not in page.url.lower()
    if not logged_in:
        for selector in SUCCESS_HINT_SELECTORS:
            try:
                if await page.locator(selector).count() > 0:
                    logged_in = True
                    break
            except Exception:
                continue
    if not logged_in:
        return LoginResult(False, "failed", "登录后仍停留在登录页，账号或密码可能错误", evidence)
    return LoginResult(True, "success", f"登录成功，当前页面：{page.url}", evidence)
