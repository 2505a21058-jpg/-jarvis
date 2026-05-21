"""
skills/automation/browser/actions.py

High-level browser actions.
Each action handles its own retries and error recovery.
"""

from __future__ import annotations

import asyncio
import logging
import os

from skills.automation.browser.controller import get_browser

logger = logging.getLogger("jarvis.browser.actions")


def _get_harness_tab():
    import asyncio

    from agent.harness.browser import get_harness

    async def _get():
        harness = get_harness()
        await harness.ensure_ready()
        return await harness.active_tab()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _get()).result(timeout=10)
        return loop.run_until_complete(_get())
    except Exception:
        return None


def _run_async(coro):
    """Run an async coroutine from sync skill code safely."""
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return asyncio.run(coro)

        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=35)
        return loop.run_until_complete(coro)
    except Exception as exc:
        logger.error("[BROWSER] _run_async failed: %s", exc)
        return None


def _normalize_url(url: str) -> str:
    target = str(url or "").strip()
    if target and not target.startswith(("http://", "https://")):
        target = "https://" + target
    return target


def _vision_verify_enabled() -> bool:
    return os.getenv("JARVIS_VISION_VERIFY", "false").lower() in {"1", "true", "yes", "on"}


async def verify_action(action: str, target: str = "") -> bool:
    """Optionally ask Gemma bridge to verify the visible browser result."""
    if not _vision_verify_enabled():
        return True

    browser = get_browser()
    screenshot_path = "jarvis_browser_verify.png"
    await browser.screenshot(screenshot_path)
    page_text = await browser.get_text(max_chars=4000)
    try:
        from skills.automation.gemma_bridge import verify_browser_action

        return bool(
            verify_browser_action(
                action=action,
                target=target,
                url=browser.current_url,
                page_text=page_text,
                screenshot_path=screenshot_path,
            )
        )
    except Exception as exc:
        logger.warning("[BROWSER] Gemma verification failed: %s", exc)
        return False


async def navigate(url: str) -> str:
    target = _normalize_url(url)
    if not target:
        return "Failed to open empty URL"

    try:
        from agent.harness.browser import get_harness

        harness = get_harness()
        if await harness.ensure_ready():
            tab = await harness.active_tab()
            if tab:
                ok = await asyncio.wait_for(tab.navigate(target), timeout=8.0)
                if ok:
                    logger.info("[BROWSER] Navigated via harness: %s", target)
                    return f"Opened {target}"
    except asyncio.TimeoutError:
        logger.debug("[BROWSER] Harness navigate timed out, falling back to Playwright")
    except Exception as exc:
        logger.debug("[BROWSER] Harness navigate unavailable: %s", exc)

    ok = await get_browser().navigate(target)
    if not ok:
        return f"Failed to open {target}"
    if not await verify_action("navigate", target):
        return f"Opened {target}, but verification failed"
    return f"Opened {target}"


async def search_youtube(query: str) -> str:
    from skills.automation.browser.selectors import find_element, get_site_selectors

    browser = get_browser()
    if not await browser.navigate("https://www.youtube.com"):
        return "Could not open YouTube"

    page = browser.page
    selectors = get_site_selectors("youtube.com", "search_input")
    el = await find_element(page, selectors, timeout=10000)
    if not el:
        return "Could not find YouTube search box"

    await el.click()
    try:
        await el.clear()
    except Exception:
        await page.keyboard.press("Control+A")
    await el.type(query, delay=40)
    await page.keyboard.press("Enter")
    await browser.wait_for_nav(timeout=10000)
    logger.info("[BROWSER] YouTube search: %s", query)

    if not await verify_action("search_youtube", query):
        return f"Searched YouTube for: {query}, but verification failed"
    return f"Searched YouTube for: {query}"


async def click_first_youtube_result() -> str:
    from skills.automation.browser.selectors import find_element, get_site_selectors

    browser = get_browser()
    selectors = get_site_selectors("youtube.com", "first_result")
    el = await find_element(browser.page, selectors, timeout=10000)
    if not el:
        return "Could not find YouTube results"

    await el.click()
    await browser.wait_for_nav(timeout=10000)
    if not await verify_action("click_first_youtube_result", browser.current_url):
        return "Clicked first YouTube result, but verification failed"
    return "Clicked first YouTube result"


async def search_in_page(query: str, site: str = "") -> str:
    from skills.automation.browser.selectors import find_element, get_site_selectors

    browser = get_browser()
    url = site or browser.current_url
    selectors = get_site_selectors(url, "search_input") or [
        'input[type="search"]',
        'input[name="q"]',
        '[aria-label*="Search"]',
        'input[placeholder*="Search"]',
        'textarea[name="q"]',
    ]
    el = await find_element(browser.page, selectors, timeout=10000)
    if not el:
        return "Could not find search box"

    await el.click()
    try:
        await el.clear()
    except Exception:
        await browser.page.keyboard.press("Control+A")
    await el.type(query, delay=35)
    await browser.page.keyboard.press("Enter")
    await browser.wait_for_nav(timeout=10000)

    if not await verify_action("search_in_page", query):
        return f"Searched for: {query}, but verification failed"
    return f"Searched for: {query}"


async def click(hint: str) -> str:
    from skills.automation.browser.selectors import find_with_fallbacks

    browser = get_browser()
    if not await browser.ensure_ready():
        return "Browser is not available"

    selectors = [hint] if any(token in hint for token in ("#", ".", "[", "xpath=", "//")) else []
    el = await find_with_fallbacks(browser.page, hint, selectors=selectors, timeout=7000)
    if el:
        await el.click()
        if not await verify_action("click", hint):
            return f"Clicked: {hint}, but verification failed"
        return f"Clicked: {hint}"

    if await browser._pyautogui_fallback_click():
        return f"Clicked fallback for: {hint}"
    return f"Could not find: {hint}"


async def type_text(text: str, selector: str | None = None) -> str:
    browser = get_browser()
    if not await browser.ensure_ready():
        return "Browser is not available"

    if selector:
        ok = await browser.type_into([selector], text)
        if ok and not await verify_action("type_text", selector):
            return "Typed text, but verification failed"
        return "Typed text" if ok else "Could not type"

    await browser.page.keyboard.type(text, delay=30)
    if not await verify_action("type_text", text[:80]):
        return "Typed text, but verification failed"
    return f"Typed: {text[:50]}"


def navigate_sync(url: str) -> str:
    return _run_async(navigate(url))


def search_youtube_sync(query: str) -> str:
    return _run_async(search_youtube(query))


def search_in_page_sync(query: str, site: str = "") -> str:
    return _run_async(search_in_page(query, site))


def click_sync(hint: str) -> str:
    return _run_async(click(hint))


def click_first_youtube_result_sync() -> str:
    return _run_async(click_first_youtube_result())
