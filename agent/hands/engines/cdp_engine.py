"""
agent/hands/engines/cdp_engine.py

CDP engine - controls Chrome and Electron apps.
Uses Browser Harness Tab directly.
Zero simulation - direct CDP commands.

Works on: Chrome, Edge, Brave, VS Code, Discord, Slack, Spotify
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any, Optional

from agent.hands.engines.base import ActionResult, fail, ok
from rawvision.output.schema import UIElement

logger = logging.getLogger("jarvis.hands.cdp")


class AwaitableValue:
    """Small adapter so direct API calls can be awaited while tests stay sync."""

    def __init__(self, coro):
        self._coro = coro

    def __await__(self):
        return self._coro.__await__()


class CDPEngine:
    """Direct CDP control via Browser Harness."""

    name = "cdp"

    def __init__(self, tab=None, cdp_port: int = 9222):
        self.tab = tab
        self.cdp_port = cdp_port

    def click(self, node_id: int | UIElement, tab=None):
        """Click DOM node by backend node ID."""
        if isinstance(node_id, UIElement):
            backend_id = node_id.cdp_node_id
            if backend_id is None:
                return fail(self.name, "element has no CDP node id")
            success = self._run(self._click_async(backend_id, tab=tab))
            return ok(self.name, "clicked", node_id=backend_id) if success else fail(self.name, "click failed", node_id=backend_id)
        return AwaitableValue(self._click_async(int(node_id), tab=tab))

    def type_text(self, text_or_element, text: Optional[str] = None, node_id: Optional[int] = None, tab=None):
        """Type text, optionally into specific node."""
        if isinstance(text_or_element, UIElement):
            element = text_or_element
            payload = str(text or "")
            backend_id = element.cdp_node_id
            success = self._run(self._type_text_async(payload, node_id=backend_id, tab=tab))
            return ok(self.name, "typed", node_id=backend_id) if success else fail(self.name, "type failed", node_id=backend_id)
        return AwaitableValue(self._type_text_async(str(text_or_element or ""), node_id=node_id, tab=tab))

    def set_value(self, node_id: int, value: str, tab=None):
        """Set input value instantly."""
        return AwaitableValue(self._set_value_async(node_id, value, tab=tab))

    def navigate(self, url: str, tab=None):
        """Navigate to URL."""
        return AwaitableValue(self._navigate_async(url, tab=tab))

    def evaluate(self, js: str, tab=None):
        """Execute JavaScript in page context."""
        return AwaitableValue(self._evaluate_async(js, tab=tab))

    def fetch(self, url: str, method="GET", body=None, tab=None):
        """Make HTTP request as the page using page cookies/auth."""
        return AwaitableValue(self._fetch_async(url, method=method, body=body, tab=tab))

    def key(self, combo: str, tab=None):
        """Press keyboard shortcut."""
        return AwaitableValue(self._key_async(combo, tab=tab))

    def scroll(self, x: int, y: int, dy: int = 300, tab=None):
        """Scroll at position."""
        return AwaitableValue(self._scroll_async(x, y, dy=dy, tab=tab))

    def wait_for(self, selector: str, timeout_ms=8000, tab=None):
        """Wait for CSS selector to appear."""
        return AwaitableValue(self._wait_for_async(selector, timeout_ms=timeout_ms, tab=tab))

    async def _click_async(self, node_id: int, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.click(node_id))

    async def _type_text_async(self, text: str, node_id: Optional[int] = None, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.type_text(text, node_id=node_id))

    async def _set_value_async(self, node_id: int, value: str, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.set_value(node_id, value))

    async def _navigate_async(self, url: str, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.navigate(url))

    async def _evaluate_async(self, js: str, tab=None) -> Any:
        t = tab or await self._get_tab()
        if not t:
            return None
        return await t.evaluate(js)

    async def _fetch_async(self, url: str, method="GET", body=None, tab=None) -> Optional[dict]:
        t = tab or await self._get_tab()
        if not t:
            return None
        return await t.fetch(url, method, body)

    async def _key_async(self, combo: str, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.key(combo))

    async def _scroll_async(self, x: int, y: int, dy: int = 300, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.scroll(x, y, delta_y=dy))

    async def _wait_for_async(self, selector: str, timeout_ms=8000, tab=None) -> bool:
        t = tab or await self._get_tab()
        if not t:
            return False
        return bool(await t.wait_for_selector(selector, timeout_ms))

    async def _get_tab(self):
        if self.tab is not None:
            return self.tab
        try:
            from agent.harness.browser import get_harness

            harness = get_harness(port=self.cdp_port)
            await harness.ensure_ready()
            self.tab = await harness.active_tab()
            return self.tab
        except Exception as e:
            logger.error("[CDP] Get tab failed: %s", e)
            return None

    @staticmethod
    def _run(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=5)
