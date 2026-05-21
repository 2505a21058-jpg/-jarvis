"""
internet/fetch.py - High quality content extraction.
"""

from __future__ import annotations

import logging
import re
import urllib.request
from typing import Dict, Optional


logger = logging.getLogger("jarvis.internet.fetch")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)
_FETCH_TIMEOUT = 4
_MAX_CONTENT_CHARS = 13000
_FETCH_OVERALL_TIMEOUT = 3.0


def fetch_page(url: str) -> Optional[str]:
    """Fetch a URL and return clean readable text."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            if "text/html" not in resp.headers.get("Content-Type", ""):
                return None
            raw_html = resp.read().decode("utf-8", errors="replace")

        return _extract_text(raw_html, url)
    except Exception as exc:
        logger.warning("[FETCH] Failed %s: %s", url, exc)
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
        threading.Thread(target=worker, daemon=True, name=f"jarvis-fetch-{index}")
        for index in range(min(max_workers, len(pending)))
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
