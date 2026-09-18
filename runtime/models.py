from dataclasses import dataclass
from typing import Any

@dataclass
class RuntimeSession:
    browser: Any
    paths: Any
    config: Any
    url: str
    system_name: str
    scope: str | None = None
    target: list[str] | None = None
