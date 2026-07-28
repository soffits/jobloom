from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from typing import Any, NoReturn
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_PROVIDER = 4
EXIT_STATE = 5
EXIT_UPSTREAM = 6


@dataclass(slots=True)
class JobLoomError(Exception):
    message: str
    exit_code: int
    code: str
    hint: str | None = None

    def payload(self) -> dict[str, object]:
        body: dict[str, object] = {"error": {"code": self.code, "message": self.message}}
        if self.hint:
            body["error"]["hint"] = self.hint  # type: ignore[index]
        return body


def fail(error: JobLoomError, fmt: str = "json") -> NoReturn:
    _ = fmt
    print(json.dumps(error.payload(), sort_keys=True), file=sys.stderr)
    raise SystemExit(error.exit_code)


def redact(text: str | None) -> str:
    if not text:
        return ""
    return redact_string(text)[:2000]


SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "cookie",
    "authorization",
    "token",
    "secret",
    "credential",
    "session",
    "li_at",
    "jsessionid",
)

SENSITIVE_QUERY_KEYS = (
    "access_token",
    "auth",
    "authorization",
    "cookie",
    "credential",
    "jsessionid",
    "li_at",
    "password",
    "passwd",
    "secret",
    "session",
    "token",
)

SECRET_PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bli_at=([^;\s&]+)"),
    re.compile(r"(?i)\bJSESSIONID=([^;\s&]+)"),
    re.compile(r"(?im)^(\s*(?:Cookie|Set-Cookie|Authorization)\s*:\s*).*$"),
    re.compile(
        rf"(?i)(\b(?:{'|'.join(re.escape(k) for k in SENSITIVE_KEY_PARTS)})\b\s*(?:=|:)\s*)[^;\s,&}}\]]+"
    ),
    re.compile(rf"(?i)([?&](?:{'|'.join(re.escape(k) for k in SENSITIVE_QUERY_KEYS)})=)[^&#\s]+"),
]
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")


def sensitive_key(key: object) -> bool:
    lowered = str(key).lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact_string(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return URL_PATTERN.sub(lambda match: strip_sensitive_query(match.group(0)), redacted)


def strip_sensitive_query(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc or not parts.query:
        return value
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
            if not sensitive_key(key)
        ],
        doseq=True,
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _redact_match(match: re.Match[str]) -> str:
    lowered = match.group(0).lower()
    if match.re.pattern.startswith("(?im)^"):
        return f"{match.group(1)}[REDACTED]"
    if lowered.startswith("bearer"):
        return "Bearer [REDACTED]"
    if lowered.startswith("li_at="):
        return "li_at=[REDACTED]"
    if lowered.startswith("jsessionid="):
        return "JSESSIONID=[REDACTED]"
    if len(match.groups()) == 1:
        return f"{match.group(1)}[REDACTED]"
    return "[REDACTED]"


def sanitize_raw(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if sensitive_key(key):
                continue
            sanitized = sanitize_raw(item)
            if sanitized is not None:
                clean[str(key)] = sanitized
        return clean
    if isinstance(value, list):
        return [item for item in (sanitize_raw(item) for item in value) if item is not None]
    if isinstance(value, tuple | set):
        return [item for item in (sanitize_raw(item) for item in value) if item is not None]
    if isinstance(value, str):
        return redact_string(value)
    return value
