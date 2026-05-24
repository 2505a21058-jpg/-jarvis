"""
skills/automation/browser/controller.py

Singleton BrowserController.
Persistent Playwright browser with crash recovery.
All browser operations go through this class.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading

logger = logging.getLogger("jarvis.browser.controller")

_HEADLESS = os.getenv("JARVIS_BROWSER_HEADLESS", "false").lower() == "true"
_TIMEOUT_MS = int(os.getenv("JARVIS_BROWSER_TIMEOUT", "30000"))


class BrowserController:
    def __init__(self):
        self._lock = threading.RLock()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._ready = False

    def _page_alive(self) -> bool:
        """Check if the stored page reference is usable."""
        page = self._page
        if page is None:
            return False
        try:
            return not page.is_closed()
        except Exception:
            return False

    async def ensure_ready(self) -> bool:
        if self._ready and self._page_alive():
            return True
        return await self._launch()

    async def _launch(self) -> bool:
        with self._lock:
            try:
                from playwright.async_api import async_playwright

                await self.close()
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=_HEADLESS,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                    ],
                )
                self._context = await self._browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                await self._context.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,ttf}", self._route_assets)
                self._page = await self._context.new_page()
                self._page.set_default_timeout(_TIMEOUT_MS)
                self._page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))
                self._ready = True
                logger.info("[BROWSER] Launched Chromium")
                return True
            except Exception as exc:
                logger.error("[BROWSER] Launch failed: %s", exc)
                self._ready = False
                return False

    async def _route_assets(self, route):
        url = route.request.url.lower()
        if any(key in url for key in ("youtube", "google", "spotify")):
            await route.continue_()
        else:
            await route.abort()

    async def _safe_page(self):
        """Return page if alive, else attempt recovery."""
        if self._page_alive():
            return self._page
        ok = await self._launch()
        return self._page if ok else None

    async def navigate(self, url: str) -> bool:
        page = await self._safe_page()
        if not page:
            return False
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=_TIMEOUT_MS)
            logger.info("[BROWSER] -> %s", url)
            return True
        except Exception as exc:
            logger.error("[BROWSER] navigate failed: %s", exc)
            await self._try_recover()
            return False

    async def click(self, selectors: list[str], timeout: int = 5000) -> bool:
        page = await self._safe_page()
        if not page:
            return False
        from skills.automation.browser.selectors import find_element

        el = await find_element(page, selectors, timeout)
        if el:
            try:
                await el.click()
                return True
            except Exception as exc:
                logger.warning("[BROWSER] click failed: %s", exc)
        return await self._pyautogui_fallback_click()

    async def type_into(self, selectors: list[str], text: str, clear_first: bool = True) -> bool:
        page = await self._safe_page()
        if not page:
            return False
        from skills.automation.browser.selectors import find_element

        el = await find_element(page, selectors)
        if el:
            try:
                if clear_first:
                    await el.clear()
                await el.type(text, delay=30)
                return True
            except Exception as exc:
                logger.warning("[BROWSER] type_into failed: %s", exc)
        return False

    async def wait_for_nav(self, timeout: int = 10000) -> bool:
        page = self._page if self._page_alive() else None
        if not page:
            return False
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except Exception:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
                return True
            except Exception:
                return False

    async def get_text(self, max_chars: int = 5000) -> str:
        page = self._page if self._page_alive() else None
        if not page:
            return ""
        try:
            return (await page.inner_text("body"))[:max_chars]
        except Exception:
            return ""

    async def screenshot(self, path: str = "jarvis_screenshot.png") -> bool:
        page = self._page if self._page_alive() else None
        if not page:
            return False
        try:
            await page.screenshot(path=path)
            return True
        except Exception:
            return False

    @property
    def page(self):
        return self._page if self._page_alive() else None

    @property
    def current_url(self) -> str:
        try:
            p = self._page
            return p.url if p and not p.is_closed() else ""
        except Exception:
            return ""

    async def _try_recover(self) -> bool:
        logger.warning("[BROWSER] Attempting recovery...")
        try:
            if self._page_alive():
                await self._page.reload(wait_until="domcontentloaded", timeout=5000)
                return True
        except Exception:
            pass
        with self._lock:
            await self.close()
            return await self._launch()

    async def _pyautogui_fallback_click(self) -> bool:
        logger.warning("[BROWSER] Falling back to pyautogui")
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            width, height = pyautogui.size()
            pyautogui.click(width // 2, height // 2)
            return True
        except Exception as exc:
            logger.error("[BROWSER] pyautogui fallback failed: %s", exc)
            return False

    async def close(self):
        with self._lock:
            for attr in ("_page", "_context", "_browser"):
                obj = getattr(self, attr, None)
                if obj:
                    try:
                        await obj.close()
                    except Exception:
                        pass
                    setattr(self, attr, None)
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
            self._ready = False


_browser_instance: BrowserController | None = None


def get_browser() -> BrowserController:
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = BrowserController()
    return _browser_instance
