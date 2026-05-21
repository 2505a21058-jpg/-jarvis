"""
internet/web_agent.py - Main internet research orchestrator.
"""

from __future__ import annotations

import logging
import time
import urllib.parse

from internet.fetch import fetch_multiple
from internet.search import search
from internet.synthesize import format_quick_results, synthesize


logger = logging.getLogger("jarvis.internet.web_agent")

_SKIP_FETCH_DOMAINS = {"news.google.com", "duckduckgo.com"}


def _should_fetch(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return bool(host) and host not in _SKIP_FETCH_DOMAINS


def research(query: str, depth: str = "normal", format: str = "auto") -> str:
    """Run search -> optional fetch -> synthesis."""
    start = time.monotonic()
    max_results = {"quick": 3, "normal": 5, "deep": 7}.get(depth, 5)
    results = search(query, max_results=max_results)
    if not results:
        return f"No results found for: {query}"

    if depth == "quick":
        answer = format_quick_results(query, results)
    else:
        fetch_count = 3 if depth == "normal" else 5
        urls = [result.url for result in results if _should_fetch(result.url)][:fetch_count]
        page_texts = fetch_multiple(urls, max_workers=3)
        answer = synthesize(query, results, page_texts, format=format)

    elapsed = (time.monotonic() - start) * 1000
    logger.info("[WEB] '%s' completed in %.0fms (%s mode)", query, elapsed, depth)
    return answer


def quick_answer(query: str) -> str:
    return research(query, depth="quick")


def deep_research(query: str, depth: int = 4, format: str = "auto") -> str:
    """Multi-query parallel research via internet/deep_research.py."""
    from internet.deep_research import deep_research as _deep_research
    return _deep_research(query, depth=depth, format=format)
