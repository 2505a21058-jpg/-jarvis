"""
internet/fetch.py - High quality content extraction.
Fetches pages using `requests` (primary) with stdlib `urllib.request` fallback.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional
from urllib.parse import urljoin

from internet.url_safety import is_safe_fetch_url


logger = logging.getLogger("jarvis.internet.fetch")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)
_FETCH_TIMEOUT = 10
_MAX_CONTENT_CHARS = 50000
_FETCH_OVERALL_TIMEOUT = 8.0

# Session cache: avoid re-fetching same URL within 5 minutes
_page_cache: dict[str, tuple[str, float]] = {}
_PAGE_CACHE_TTL = 300


def _get_cached(url: str) -> str | None:
    entry = _page_cache.get(url)
    if entry and (time.monotonic() - entry[1]) < _PAGE_CACHE_TTL:
        return entry[0]
    if url in _page_cache:
        del _page_cache[url]
    return None


def _set_cached(url: str, text: str):
    _page_cache[url] = (text, time.monotonic())


def clear_page_cache():
    _page_cache.clear()


def _fetch_with_requests(url: str) -> str | None:
    """Fetch a URL using the `requests` library (connection pooling, redirects)."""
    import requests as _requests
    current_url = url
    try:
        for _ in range(4):
            if not is_safe_fetch_url(current_url):
                logger.warning("[FETCH] Blocked unsafe URL: %s", current_url)
                return None
            resp = _requests.get(
                current_url,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=_FETCH_TIMEOUT,
                allow_redirects=False,
            )
            if 300 <= resp.status_code < 400 and resp.headers.get("Location"):
                current_url = urljoin(current_url, resp.headers["Location"])
                continue
            break
        else:
            return None
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None
        raw_html = resp.text
        return _extract_text(raw_html, current_url)
    except Exception as exc:
        logger.debug("[FETCH] requests failed for %s: %s", url, exc)
        return None


def _fetch_with_urllib(url: str) -> str | None:
    """Fallback fetcher using stdlib urllib."""
    import urllib.request

    class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            redirected = urljoin(req.full_url, newurl)
            if not is_safe_fetch_url(redirected):
                logger.warning("[FETCH] Blocked unsafe redirect: %s", redirected)
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        if not is_safe_fetch_url(url):
            logger.warning("[FETCH] Blocked unsafe URL: %s", url)
            return None
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        opener = urllib.request.build_opener(_SafeRedirectHandler)
        with opener.open(req, timeout=_FETCH_TIMEOUT) as resp:
            if "text/html" not in resp.headers.get("Content-Type", ""):
                return None
            raw_html = resp.read().decode("utf-8", errors="replace")
        return _extract_text(raw_html, url)
    except Exception as exc:
        logger.debug("[FETCH] urllib failed for %s: %s", url, exc)
        return None


def fetch_page(url: str) -> Optional[str]:
    """Fetch a URL and return clean readable text (cached for 5 min)."""
    if not is_safe_fetch_url(url):
        logger.warning("[FETCH] Blocked unsafe URL: %s", url)
        return None
    cached = _get_cached(url)
    if cached is not None:
        return cached
    text = _fetch_with_requests(url)
    if text:
        _set_cached(url, text)
        return text
    text = _fetch_with_urllib(url)
    if text:
        _set_cached(url, text)
        return text
    logger.warning("[FETCH] All fetchers failed for %s", url)
    return None


def _extract_text(raw_html: str, url: str) -> Optional[str]:
    """Extract article-quality text, preferring trafilatura when installed."""
    try:
        import trafilatura

        text = trafilatura.extract(
            raw_html,
            url=url,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
        )
        if text and len(text) > 120:
            return text[:_MAX_CONTENT_CHARS]
    except Exception:
        pass

    text = re.sub(
        r"<(script|style)[^>]*>.*?</\1>",
        " ",
        raw_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_CONTENT_CHARS] if len(text) > 80 else None


def fetch_multiple(urls: list[str], max_workers: int = 3) -> Dict[str, Optional[str]]:
    """Fetch several URLs concurrently."""
    import threading
    import time

    results: dict[str, Optional[str]] = {}
    pending = list(urls)
    lock = threading.Lock()
    deadline = time.monotonic() + _FETCH_OVERALL_TIMEOUT

    def worker() -> None:
        while True:
            with lock:
                if not pending:
                    return
                url = pending.pop(0)
            try:
                text = fetch_page(url)
            except Exception:
                text = None
            with lock:
                results[url] = text

    threads = [
        threading.Thread(target=worker, daemon=True, name=f"jarvis-fetch-{idx}")
        for idx in range(min(max_workers, len(pending)))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        remaining = max(0, deadline - time.monotonic())
        if remaining <= 0:
            break
        thread.join(timeout=remaining)

    for url in urls:
        results.setdefault(url, None)
    return results
