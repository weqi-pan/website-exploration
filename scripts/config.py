from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from urllib.parse import urlparse


def normalize_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("URL 不能为空")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"无效的网站 URL: {value}")
    return value


@dataclass(frozen=True)
class NavSelectors:
    menu_items: str = ""
    cards: str = ""
    tabs: str = ""


@dataclass(frozen=True)
class LoginSelectors:
    username_input: str = ""
    password_input: str = ""
    submit_button: str = ""


@dataclass(frozen=True)
class ExplorationConfig:
    name: str = ""
    login_url: str = ""
    username: str = ""
    password: str = ""
    nav_mode: str = "none"
    nav_selectors: NavSelectors = field(default_factory=NavSelectors)
    login_selectors: LoginSelectors = field(default_factory=LoginSelectors)
    allow_form_submit: bool = False
    blocked_action_keywords: tuple[str, ...] = ()
    timeout_ms: int = 30000

    @property
    def has_login(self) -> bool:
        return bool(self.login_url and self.username and self.password)

    @classmethod
    def from_json(cls, path: Path | str) -> "ExplorationConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        nav_raw = data.get("navSelectors") or {}
        login_raw = data.get("loginSelectors") or {}
        keywords = data.get("blockedActionKeywords") or []
        allow_form_submit = data.get("allowFormSubmit", False)
        if not isinstance(allow_form_submit, bool):
            raise ValueError("allowFormSubmit must be a boolean")
        return cls(
            name=data.get("name", ""),
            login_url=data.get("loginUrl", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            nav_mode=data.get("navMode", "auto"),
            nav_selectors=NavSelectors(
                menu_items=nav_raw.get("menuItems", ""),
                cards=nav_raw.get("cards", ""),
                tabs=nav_raw.get("tabs", ""),
            ),
            login_selectors=LoginSelectors(
                username_input=login_raw.get("usernameInput", ""),
                password_input=login_raw.get("passwordInput", ""),
                submit_button=login_raw.get("submitButton", ""),
            ),
            allow_form_submit=allow_form_submit,
            blocked_action_keywords=tuple(str(k) for k in keywords),
            timeout_ms=int(data.get("timeout", 30000)),
        )
