"""
skills/automation/hero/actions.py

High-level Hero actions.
Used by open_and_search, open_search_and_play etc.
Drop-in replacement for browser/actions.py for web tasks.
"""

from __future__ import annotations
import logging
from typing import Optional

from skills.automation.hero.browser import get_hero
from skills.automation.hero.setup import ensure_hero_running

logger = logging.getLogger("jarvis.hero.actions")


def _ensure() -> bool:
    """Ensure Hero is running before any action."""
    return ensure_hero_running()


def navigate(url: str) -> str:
    if not _ensure():
        return "Hero not available — falling back to Playwright"
    ok = get_hero().navigate(url)
    return f"Opened {url}" if ok else f"Failed to open {url}"


def search_youtube(query: str) -> str:
    if not _ensure():
        from skills.automation.browser.actions import search_youtube_sync
        return search_youtube_sync(query)

    hero = get_hero()
    hero.navigate("https://www.youtube.com")

    clicked = hero.click(selector='input#search')
    if not clicked:
        clicked = hero.click(text="Search")
    if not clicked:
        return "Could not find YouTube search box"

    hero.type_text(query)
    hero.evaluate("document.querySelector('input#search').form.submit()")

    hero.wait_for('ytd-video-renderer', timeout_ms=10000)
    logger.info("[HERO] YouTube search: %s", query)
    return f"Searched YouTube for: {query}"


def click_first_youtube_result() -> str:
    if not _ensure():
        from skills.automation.browser.actions import (
            click_first_youtube_result_sync
        )
        return click_first_youtube_result_sync()

    hero = get_hero()
    selectors = [
        'ytd-video-renderer a#video-title',
        'ytd-rich-item-renderer a#video-title',
        'a#video-title',
    ]
    for sel in selectors:
        if hero.click(selector=sel):
            hero.wait_for('.ytp-play-button', timeout_ms=8000)
            return "Clicked first YouTube result"

    return "Could not find YouTube results"


def search_google(query: str) -> str:
    if not _ensure():
        from skills.automation.browser.actions import (
            navigate_sync, search_in_page_sync
        )
        navigate_sync("https://www.google.com")
        return search_in_page_sync(query, "google.com")

    hero = get_hero()
    hero.navigate(f"https://www.google.com/search?q={query}")
    return f"Searched Google for: {query}"
