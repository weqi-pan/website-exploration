from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_AUTHORIZATION_PATTERN = re.compile(
    r"\bauthorization\s*[:=]\s*(?:bearer\s+)?[^\s,;]+", re.IGNORECASE
)
_BEARER_PATTERN = re.compile(r"\bbearer\s+[^\s,;]+", re.IGNORECASE)
_ASSIGNMENT_PATTERN = re.compile(
    r"\b(api[_-]?key|apikey|password|token|secret)\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)",
    re.IGNORECASE,
)


def safe_url(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _safe_readable_url(value: str) -> str:
    parsed = urlsplit(value)
    base = urlsplit(safe_url(value))
    query = urlencode(
        [
            (name, item)
            for name, item in parse_qsl(parsed.query, keep_blank_values=True)
            if name.casefold() not in SENSITIVE_NAMES
        ]
    )
    return urlunsplit((base.scheme, base.netloc, base.path, query, ""))


def safe_text(value: object) -> str:
    text = str(value)
    text = _URL_PATTERN.sub(lambda match: _safe_readable_url(match.group(0)), text)
    text = _AUTHORIZATION_PATTERN.sub("Authorization: [REDACTED]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)
    return _ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}=[REDACTED]", text
    )


def safe_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).casefold() in SENSITIVE_NAMES
                else safe_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_value(item) for item in value]
    if isinstance(value, str):
        return safe_text(value)
    return value
