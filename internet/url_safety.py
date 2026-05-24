"""URL safety checks for fetch/research code."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


_ALLOW_PRIVATE_ENV = "JARVIS_ALLOW_PRIVATE_FETCH"
_LOCAL_NAMES = {"localhost", "localhost.localdomain"}


def _allow_private_fetch() -> bool:
    return os.getenv(_ALLOW_PRIVATE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_blocked_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(
        (
            ip.is_loopback,
            ip.is_private,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def is_safe_fetch_url(url: str, *, resolve: bool = True) -> bool:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if _allow_private_fetch():
        return True
    if host in _LOCAL_NAMES or _is_blocked_ip(host):
        return False
    if not resolve:
        return True
    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return all(not _is_blocked_ip(info[4][0]) for info in infos)
