"""
internet/deep_research.py — Multi-query parallel web research engine.
Takes a topic, generates sub-questions, searches each in parallel,
fetches results, and synthesizes a comprehensive answer.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from internet.search import search, SearchResult
from internet.fetch import fetch_page
from internet.synthesize import synthesize

logger = logging.getLogger("jarvis.internet.deep_research")

_DECOMPOSE_SYSTEM = (
    "You are a research strategist. Given a user's research topic, "
    "generate {n} specific web search queries that together cover the "
    "topic comprehensively from different angles. "
    "Return ONLY a JSON array of strings, no other text. "
    "Each query should be 5-15 words, focused, and search-engine-optimized."
)


def decompose_query(topic: str, n: int = 4) -> list[str]:
    prompt = _DECOMPOSE_SYSTEM.format(n=max(1, n))
    user = f"Research topic: {topic}\n\nGenerate {n} search queries."
    try:
        from models.llm import call_llm_json
        result = call_llm_json(system=prompt, user=user, temperature=0.3, max_tokens=300)
        if isinstance(result, list):
            queries = [str(q).strip().strip('"').strip("'") for q in result if str(q).strip()]
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
    host = urllib.parse.urlparse(url).netloc.lower()
    skip_domains = {"news.google.com", "duckduckgo.com", "twitter.com", "x.com", "reddit.com"}
    return bool(host) and host not in skip_domains


def _fetch_pages(results: list[SearchResult], max_fetch: int = 6) -> dict[str, Optional[str]]:
    urls = [r.url for r in results if _should_fetch(r.url)][:max_fetch]
    page_texts: dict[str, Optional[str]] = {}

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch_page, url): url for url in urls}
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


def deep_research(topic: str, depth: int = 4, format: str = "auto") -> str:
    start = time.monotonic()

    queries = decompose_query(topic, n=depth)
    results = parallel_search(queries, workers=min(4, len(queries)))
    if not results:
        return f"No search results found for: {topic}"

    page_texts = _fetch_pages(results, max_fetch=depth + 2)
    answer = synthesize(topic, results, page_texts, format=format)

    elapsed = (time.monotonic() - start) * 1000
    logger.info("[DEEP] '%s' completed in %.0fms (%d queries, %d results)",
                topic, elapsed, len(queries), len(results))
    return answer
