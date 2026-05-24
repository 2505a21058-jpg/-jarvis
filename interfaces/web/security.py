"""Small authentication helpers for the local web UI."""

from __future__ import annotations

import os
import secrets
from collections.abc import Mapping
from urllib.parse import urlparse


_TOKEN_ENV = "JARVIS_WEB_TOKEN"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def configured_web_token() -> str:
    return os.getenv(_TOKEN_ENV, "").strip()


def _headers_lower(headers: Mapping[str, str] | None) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in (headers or {}).items()}


def _header_token(headers: Mapping[str, str] | None) -> str:
    lowered = _headers_lower(headers)
    direct = lowered.get("x-jarvis-token", "").strip()
    if direct:
        return direct
    authorization = lowered.get("authorization", "").strip()
    prefix = "bearer "
    if authorization.lower().startswith(prefix):
        return authorization[len(prefix):].strip()
    return ""


def is_web_request_authorized(
    headers: Mapping[str, str] | None,
    query_token: str | None = None,
) -> bool:
    expected = configured_web_token()
    if not expected:
        return True
    provided = str(query_token or "").strip() or _header_token(headers)
    return bool(provided) and secrets.compare_digest(provided, expected)


def _host_name(host: str) -> str:
    text = str(host or "").strip().lower()
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")]
    return text.rsplit(":", 1)[0] if ":" in text else text


def is_safe_web_origin(origin: str | None, request_host: str) -> bool:
    if not origin:
        return True
    parsed = urlparse(str(origin))
    origin_host = _host_name(parsed.netloc or parsed.path)
    host = _host_name(request_host)
    if not origin_host or not host:
        return False
    if origin_host == host:
        return True
    return origin_host in _LOCAL_HOSTS and host in _LOCAL_HOSTS
