"""
internet/search.py - Fast + robust DuckDuckGo search.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List


logger = logging.getLogger("jarvis.internet.search")

_DDGO_URL = "https://html.duckduckgo.com/html/"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)
_LAST_SEARCH_TIME = 0.0
_MIN_SEARCH_INTERVAL = 1.3


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    position: int


def search(query: str, max_results: int = 6) -> List[SearchResult]:
    """Search DuckDuckGo HTML and return ranked results."""
    global _LAST_SEARCH_TIME

    elapsed = time.time() - _LAST_SEARCH_TIME
    if elapsed < _MIN_SEARCH_INTERVAL:
        time.sleep(max(0, _MIN_SEARCH_INTERVAL - elapsed))

    try:
        params = urllib.parse.urlencode({"q": query, "kl": "us-en"})
        req = urllib.request.Request(
            f"{_DDGO_URL}?{params}",
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")

        _LAST_SEARCH_TIME = time.time()
        results = _parse_ddgo_html(raw_html, max_results)
        logger.info("[SEARCH] '%s' -> %s results", query, len(results))
        return results
    except Exception as exc:
        logger.error("[SEARCH] Failed: %s", exc)
        return []


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_result_url(href: str) -> str:
    href = html_lib.unescape(str(href or "").strip())
    if href.startswith("//duckduckgo.com/l/"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        uddg = query.get("uddg", [""])[0]
        return urllib.parse.unquote(uddg).strip()
    return href


def _parse_ddgo_html(raw_html: str, max_results: int) -> List[SearchResult]:
    """Parse a DuckDuckGo HTML results page."""
    results: list[SearchResult] = []
    title_matches = list(
        re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            raw_html,
            re.DOTALL | re.IGNORECASE,
        )
    )

    for index, match in enumerate(title_matches):
        next_start = title_matches[index + 1].start() if index + 1 < len(title_matches) else len(raw_html)
        block = raw_html[match.end():next_start]
        url = _resolve_result_url(match.group(1))
        if not url.startswith(("http://", "https://")) or "duckduckgo.com" in url:
            continue

        title = _clean_html_text(match.group(2))
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        snippet = _clean_html_text(snippet_match.group(1)) if snippet_match else ""

        if title and len(title) > 3:
            results.append(
                SearchResult(
                    title=title[:220],
                    url=url,
                    snippet=snippet[:320],
                    position=len(results) + 1,
                )
            )
            if len(results) >= max_results:
                break

    if results:
        return results

    blocks = re.findall(
        r'<div[^>]*class="[^"]*result__body[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>',
        raw_html,
        re.DOTALL | re.IGNORECASE,
    )

    for block in blocks:
        url_match = re.search(r'href="(https?://[^"]+)"', block)
        if not url_match:
            continue

        url = _resolve_result_url(url_match.group(1))
        if not url.startswith(("http://", "https://")) or "duckduckgo.com" in url:
            continue

        title_match = re.search(
            r'<a[^>]*class="result__a"[^>]*>(.*?)</a>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block,
            re.DOTALL | re.IGNORECASE,
        )
        title = _clean_html_text(title_match.group(1)) if title_match else ""
        snippet = _clean_html_text(snippet_match.group(1)) if snippet_match else ""

        if title and len(title) > 3:
            results.append(
                SearchResult(
                    title=title[:220],
                    url=url,
                    snippet=snippet[:320],
                    position=len(results) + 1,
                )
            )
            if len(results) >= max_results:
                break

    return results
