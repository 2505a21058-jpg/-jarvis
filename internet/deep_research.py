"""
internet/deep_research.py — Multi-query parallel web research engine.
Takes a topic, generates sub-questions, searches each in parallel,
fetches results, and synthesizes a comprehensive answer.
Supports multi-round fetching (follow links within pages).
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from internet.fetch import fetch_page
from internet.search import SearchResult, search
from internet.synthesize import synthesize
from internet.url_safety import is_safe_fetch_url

logger = logging.getLogger("jarvis.internet.deep_research")

_DECOMPOSE_SYSTEM = (
    "You are a research strategist. Given a user's research topic, "
    "generate {n} specific web search queries that together cover the "
    "topic comprehensively from different angles. "
    "Return ONLY a JSON array of strings, no other text. "
    "Each query should be 5-15 words, focused, and search-engine-optimized."
)

# Session cache: avoid re-fetching the same URL within one research session
_page_cache: dict[str, str] = {}


def _get_cached_or_fetch(url: str) -> Optional[str]:
    if url in _page_cache:
        logger.debug("[DEEP] Cache hit: %s", url)
        return _page_cache[url]
    text = fetch_page(url)
    if text:
        _page_cache[url] = text
    return text


def clear_cache():
    _page_cache.clear()


def decompose_query(topic: str, n: int = 4) -> list[str]:
    prompt = _DECOMPOSE_SYSTEM.format(n=max(1, n))
    user = f"Research topic: {topic}\n\nGenerate {n} search queries."
    try:
        from models.llm import call_llm
        raw = call_llm(system=prompt, user=user, temperature=0.3, max_tokens=300, timeout=60)
        raw_clean = raw.strip()
        if raw_clean.startswith("```"):
            parts = raw_clean.split("```")
            raw_clean = parts[1] if len(parts) > 1 else raw_clean
            if raw_clean.startswith("json"):
                raw_clean = raw_clean[4:].strip()
        parsed = json.loads(raw_clean)
        queries: list[str] = []
        if isinstance(parsed, list):
            queries = [str(q).strip().strip('"').strip("'") for q in parsed if str(q).strip()]
        elif isinstance(parsed, dict):
            for val in parsed.values():
                if isinstance(val, list):
                    queries = [str(q).strip().strip('"').strip("'") for q in val if str(q).strip()]
                    break
        valid = [q for q in queries if len(q) > 5][:max(1, n)]
        if valid:
            logger.info("[DEEP] Decomposed into %d sub-queries", len(valid))
            return valid
    except Exception as exc:
        logger.warning("[DEEP] Decompose failed: %s", exc)

    logger.info("[DEEP] Using original query as fallback")
    return [topic]


def parallel_search(queries: list[str], workers: int = 4, max_results_per_query: int = 5) -> list[SearchResult]:
    seen_urls: set[str] = set()
    all_results: list[SearchResult] = []
    position = 0

    with ThreadPoolExecutor(max_workers=min(workers, len(queries))) as pool:
        futures = {pool.submit(search, q, max_results=max_results_per_query): q for q in queries}
        for future in as_completed(futures):
            try:
                results = future.result()
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        position += 1
                        all_results.append(SearchResult(
                            title=r.title, url=r.url,
                            snippet=r.snippet, position=position,
                        ))
            except Exception as exc:
                logger.warning("[DEEP] Search failed for '%s': %s", futures[future], exc)

    logger.info("[DEEP] %d unique results from %d queries", len(all_results), len(queries))
    return all_results


def _should_fetch(url: str) -> bool:
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    skip_domains = {"news.google.com", "duckduckgo.com", "twitter.com", "x.com"}
    return bool(host) and host not in skip_domains and is_safe_fetch_url(url, resolve=False)


def _fetch_pages(results: list[SearchResult], max_fetch: int = 15) -> dict[str, Optional[str]]:
    urls = [r.url for r in results if _should_fetch(r.url)][:max_fetch]
    page_texts: dict[str, Optional[str]] = {}

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_get_cached_or_fetch, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                text = future.result()
                if text and len(text) > 80:
                    page_texts[url] = text
                else:
                    page_texts[url] = None
            except Exception as exc:
                logger.debug("[DEEP] Fetch failed for %s: %s", url, exc)
                page_texts[url] = None

    fetched = sum(1 for v in page_texts.values() if v)
    logger.info("[DEEP] Fetched %d/%d pages", fetched, len(urls))
    return page_texts


def _extract_new_urls(page_texts: dict[str, Optional[str]], existing_urls: set[str], max_new: int = 5) -> list[str]:
    """Extract URLs from fetched page content for a second round of fetching."""
    import re
    new_urls = []
    for text in page_texts.values():
        if not text:
            continue
        found = re.findall(r'https?://[^\s"\'<>)]+', text)
        for url in found:
            url = url.rstrip(".,;!?)]")
            if url not in existing_urls and _should_fetch(url) and url not in new_urls:
                new_urls.append(url)
                if len(new_urls) >= max_new:
                    return new_urls
    return new_urls


def deep_research(topic: str, depth: int = 4, format: str = "auto") -> str:
    start = time.monotonic()

    queries = decompose_query(topic, n=depth)
    results = parallel_search(queries, workers=min(4, len(queries)))
    if not results:
        return f"No search results found for: {topic}"

    urls_so_far = {r.url for r in results}
    page_texts = _fetch_pages(results, max_fetch=depth + 2)

    # Multi-round: extract new URLs from fetched pages and fetch more
    new_urls = _extract_new_urls(page_texts, urls_so_far, max_new=5)
    if new_urls:
        logger.info("[DEEP] Multi-round: fetching %d additional URLs from page content", len(new_urls))
        with ThreadPoolExecutor(max_workers=3) as pool:
            second_round: dict[str, Optional[str]] = {}
            futures = {pool.submit(_get_cached_or_fetch, url): url for url in new_urls}
            for future in as_completed(futures):
                url = futures[future]
                try:
                    text = future.result()
                    if text and len(text) > 80:
                        second_round[url] = text
                except Exception:
                    pass
            page_texts.update(second_round)
        round2_count = sum(1 for v in second_round.values() if v)
        logger.info("[DEEP] Multi-round: fetched %d/%d additional pages", round2_count, len(new_urls))

    answer = synthesize(topic, results, page_texts, format=format)

    elapsed = (time.monotonic() - start) * 1000
    logger.info("[DEEP] '%s' completed in %.0fms (%d queries, %d results, multi-round=%d)",
                topic, elapsed, len(queries), len(results), len(new_urls))
    return answer
