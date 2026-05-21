"""
skills/automation/browser/selectors.py

Self-healing selector system.
Tries multiple selectors before failing.
Site-specific maps handle YouTube/Google/Gmail/Spotify layout changes.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("jarvis.browser.selectors")

_SITE_SELECTORS = {
    "youtube": {
        "search_input": [
            'input#search',
            'input[name="search_query"]',
            '[placeholder*="Search"]',
            'ytd-searchbox input',
        ],
        "search_button": [
            'button#search-icon-legacy',
            'button[aria-label*="Search"]',
            '#search-icon-legacy',
        ],
        "first_result": [
            'ytd-video-renderer:first-of-type #video-title',
            'ytd-video-renderer:first-of-type a#video-title',
            'a#video-title',
        ],
        "play_button": [
            '.ytp-play-button',
            'button[aria-label*="Play"]',
            '.ytp-large-play-button',
        ],
    },
    "google": {
        "search_input": [
            'textarea[name="q"]',
            'input[name="q"]',
            '[aria-label="Search"]',
        ],
        "first_result": [
            '#search .g:first-of-type h3',
            'div#search a:first-of-type h3',
            'h3.LC20lb:first-of-type',
        ],
    },
    "gmail": {
        "compose": ['[gh="cm"]', '.T-I.J-J5-Ji.T-I-KE'],
        "to_field": ['[name="to"]', '[aria-label*="To"]'],
        "subject_field": ['[name="subjectbox"]', '[aria-label*="Subject"]'],
        "body_field": ['[aria-label*="Message Body"]', 'div[role="textbox"]'],
        "send_button": ['[data-tooltip*="Send"]', '.T-I.J-J5-Ji.aoO'],
    },
    "spotify": {
        "search_input": [
            'input[data-testid="search-input"]',
            'input[placeholder*="Artists, songs"]',
        ],
        "first_result": [
            '[data-testid="tracklist-row"]:first-of-type',
        ],
    },
}


def get_site_selectors(url: str, element_type: str) -> list[str]:
    """Get known-good selectors for a site + element type."""
    url_lower = str(url or "").lower()
    if "mail.google" in url_lower:
        return list(_SITE_SELECTORS["gmail"].get(element_type, []))
    for site_key, selectors in _SITE_SELECTORS.items():
        if site_key in url_lower:
            return list(selectors.get(element_type, []))
    return []


async def find_element(page, selectors: list[str], timeout: int = 5000):
    """
    Try each CSS/XPath selector in order, return first visible match.
    Returns a Playwright locator or None.
    """
    if page is None:
        return None

    for selector in selectors:
        if not selector:
            continue
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            logger.debug("[SELECTOR] Hit: %s", selector)
            return locator
        except Exception:
            continue
    logger.warning("[SELECTOR] All %s selectors failed", len(selectors))
    return None


async def find_by_text(page, text: str, timeout: int = 5000):
    """Find element by visible text content."""
    if page is None or not text:
        return None
    try:
        locator = page.get_by_text(text, exact=False).first
        await locator.wait_for(state="visible", timeout=timeout)
        return locator
    except Exception:
        return None


async def find_by_role(page, role: str, name: str | None = None, timeout: int = 5000):
    """Find element by ARIA role."""
    if page is None:
        return None
    try:
        kwargs = {"name": name} if name else {}
        locator = page.get_by_role(role, **kwargs).first
        await locator.wait_for(state="visible", timeout=timeout)
        return locator
    except Exception:
        return None


async def find_with_fallbacks(page, hint: str, selectors: list[str] | None = None, timeout: int = 5000):
    """Try CSS/XPath selectors, text, then common roles for an interactive target."""
    locator = await find_element(page, selectors or [], timeout=timeout)
    if locator:
        return locator

    text = str(hint or "").strip()
    if not text:
        return None

    xpath = f"xpath=//*[contains(normalize-space(), {text!r})]"
    locator = await find_element(page, [xpath], timeout=timeout)
    if locator:
        return locator

    locator = await find_by_text(page, text, timeout=timeout)
    if locator:
        return locator

    for role in ("button", "link", "textbox", "menuitem"):
        locator = await find_by_role(page, role, name=text, timeout=timeout)
        if locator:
            return locator
    return None
