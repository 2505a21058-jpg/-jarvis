"""
internet/synthesize.py - Perplexity-style synthesis.
"""

from __future__ import annotations

import logging
from typing import Optional

from internet.search import SearchResult


logger = logging.getLogger("jarvis.internet.synthesize")

_MAX_SOURCES = 4
_MAX_CHARS_PER_SOURCE = 2200
_SYNTHESIS_TIMEOUT = 30

_SYNTHESIS_SYSTEM = """You are a research assistant. Synthesize the provided sources into a clear, accurate answer.
- Cite sources with [1], [2], etc.
- Be concise but complete
- Only use information from the sources
- Note conflicts if any"""

_FORMAT_INSTRUCTIONS = {
    "text": "",
    "table": (
        "\n\nFORMAT: Output your answer as a markdown table.\n"
        "Put the dimensions being compared in the left column.\n"
        "Use the items/topics being compared as column headers.\n"
        "Include a row for each relevant comparison dimension.\n"
        "Add a summary row at the bottom."
    ),
    "sections": (
        "\n\nFORMAT: Organize your answer into sections.\n"
        "Use ## headings for each major aspect.\n"
        "Include 2-5 paragraphs per section.\n"
        "End with a brief summary."
    ),
    "bullets": (
        "\n\nFORMAT: Output as categorized bullet lists.\n"
        "Use a bold header for each category.\n"
        "Use - bullets for items under each category.\n"
        "Keep entries concise (1-2 lines each)."
    ),
}


def _detect_format(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("compare", " vs ", "versus", "differences", "comparison")):
        return "table"
    if any(w in q for w in ("list", "features", "pros", "cons", "advantages", "disadvantages")):
        return "bullets"
    if any(w in q for w in ("overview", "explain", "describe", "what are", "tell me about")):
        return "sections"
    return "text"


def format_quick_results(query: str, results: list[SearchResult]) -> str:
    """Fast non-LLM answer for quick search mode."""
    lines = []
    for index, result in enumerate(results[:5]):
        snippet = result.snippet or "No snippet available."
        lines.append(f"[{index + 1}] {result.title}\n{snippet}\nSource: {result.url}")
    if not lines:
        return f"No results found for: {query}"
    return f"Quick search results for '{query}':\n\n" + "\n\n".join(lines)


def _call_synthesis_llm(system: str, user: str) -> str:
    """Call the main LLM once with enough time for local synthesis."""
    from models.llm import call_llm

    return call_llm(
        system=system,
        user=user,
        temperature=0.2,
        max_tokens=700,
        timeout=_SYNTHESIS_TIMEOUT,
    ).strip()


def synthesize(
    query: str,
    results: list[SearchResult],
    page_texts: dict[str, Optional[str]],
    format: str = "auto",
) -> str:
    """Synthesize search results and fetched page text into one answer."""
    source_blocks: list[str] = []
    for index, result in enumerate(results[:_MAX_SOURCES]):
        text = page_texts.get(result.url) or result.snippet
        if text and len(text) > 50:
            block = (
                f"[{index + 1}] {result.title}\n"
                f"URL: {result.url}\n"
                f"{text[:_MAX_CHARS_PER_SOURCE]}"
            )
            source_blocks.append(block)

    if not source_blocks:
        return f"I couldn't find reliable information about '{query}'."

    fetched_sources = sum(
        1
        for result in results[:_MAX_SOURCES]
        if page_texts.get(result.url) and len(str(page_texts.get(result.url))) > 120
    )
    if page_texts and fetched_sources == 0:
        logger.info("[SYNTHESIZE] No extracted page text available; using quick cited fallback")
        return format_quick_results(query, results)

    if format == "auto":
        fmt = _detect_format(query)
    else:
        fmt = format if format in _FORMAT_INSTRUCTIONS else "text"

    system = _SYNTHESIS_SYSTEM + _FORMAT_INSTRUCTIONS.get(fmt, "")

    sources_text = "\n\n---\n\n".join(source_blocks)
    user_prompt = (
        f"Question: {query}\n\n"
        f"Sources:\n{sources_text}\n\n"
        "Answer using these sources only."
    )

    try:
        response = _call_synthesis_llm(system, user_prompt)
        if response:
            return response
        raise RuntimeError("empty synthesis response")
    except Exception as exc:
        logger.error("[SYNTHESIZE] Failed: %s", exc)
        return format_quick_results(query, results)
