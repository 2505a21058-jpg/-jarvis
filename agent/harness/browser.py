"""
agent/harness/browser.py

BrowserHarness - persistent CDP connection pool.
Manages connections to Chrome tabs and Electron app windows.

Single instance shared by RawVision DOM capture and Jarvis Hands CDP writes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Optional

from agent.harness.launcher import (
    ensure_chrome_debug,
    find_electron_port,
    get_chrome_tabs,
)
from agent.harness.tab import Tab

logger = logging.getLogger("jarvis.harness.browser")

_DEFAULT_PORT = 9222


class BrowserHarness:
    """
    Persistent CDP connection pool.

    Usage:
        harness = get_harness()
        await harness.ensure_ready()
        tab = await harness.active_tab()
        await tab.navigate("https://youtube.com")
    """

    def __init__(self, port: int = _DEFAULT_PORT):
        self._port = port
        self._tabs: dict[str, Tab] = {}
        self._ready = False
        self._last_refresh = 0.0

    async def ensure_ready(self) -> bool:
        """
        Ensure Chrome is running with debug port and connect to its tabs.
        Returns True if at least one connection is available.
        """
        if self._ready and self._is_still_connected(self._port):
            return True

        if not ensure_chrome_debug(self._port):
            logger.error(
                "[HARNESS] Chrome debug port %s not available. Launch Chrome with: "
                "chrome.exe --remote-debugging-port=%s",
                self._port,
                self._port,
            )
            self._ready = False
            return False

        await self._refresh_tabs()
        self._ready = self._is_still_connected(self._port)
        logger.info("[HARNESS] Ready - %d tabs connected", len(self._tabs))
        return self._ready

    async def active_tab(self) -> Optional[Tab]:
        """Get the currently active browser tab, best effort."""
        if not await self.ensure_ready():
            return None

        if time.time() - self._last_refresh > 5.0:
            await self._refresh_tabs()

        for key, tab in self._tabs.items():
            if key.startswith(f"{self._port}:") and tab._connected:
                return tab

        await self._refresh_tabs()
        return next(
            (
                tab
                for key, tab in self._tabs.items()
                if key.startswith(f"{self._port}:") and tab._connected
            ),
            None,
        )

    async def tab_for_url(self, url_fragment: str) -> Optional[Tab]:
        """Get a connected tab matching a URL fragment."""
        if not await self.ensure_ready():
            return None

        url_lower = url_fragment.lower()
        for tab in self._tabs.values():
            if tab._connected and url_lower in tab.url.lower():
                return tab

        await self._refresh_tabs()
        for tab in self._tabs.values():
            if tab._connected and url_lower in tab.url.lower():
                return tab

        return None

    async def open_tab(self, url: str) -> Optional[Tab]:
        """Open a new Chrome tab and return a connected Tab."""
        if not await self.ensure_ready():
            return None

        try:
            encoded_url = urllib.parse.quote(url, safe=":/?&=#%")
            req = urllib.request.Request(
                f"http://localhost:{self._port}/json/new?{encoded_url}",
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                tab_info = json.loads(resp.read())

            tab = await self._connect_tab(tab_info, self._port)
            if tab:
                logger.info("[HARNESS] Opened tab: %s", url)
            return tab
        except Exception as exc:
            logger.error("[HARNESS] open_tab failed: %s", exc)
            return None

    async def electron_tab(self, app_name: str) -> Optional[Tab]:
        """Connect to an Electron app CDP debug port."""
        port = find_electron_port(app_name)
        if not port:
            logger.warning("[HARNESS] Electron app '%s' not found or debug port not open", app_name)
            return None

        try:
            tab_list = get_chrome_tabs(port)
            if not tab_list:
                return None

            tab = await self._connect_tab(tab_list[0], port, default_title=app_name)
            if tab:
                logger.info("[HARNESS] Connected to %s via CDP port %s", app_name, port)
            return tab
        except Exception as exc:
            logger.error("[HARNESS] electron_tab failed for %s: %s", app_name, exc)
            return None

    async def all_tabs(self) -> list[Tab]:
        """Return all connected tabs known to the harness."""
        if self._ready:
            await self._refresh_tabs()
        return [tab for tab in self._tabs.values() if tab._connected]

    async def close(self) -> None:
        """Disconnect all tabs."""
        for tab in list(self._tabs.values()):
            await tab.disconnect()
        self._tabs.clear()
        self._ready = False

    async def _refresh_tabs(self) -> None:
        """Refresh Chrome tab list from the configured debug port."""
        try:
            tab_list = get_chrome_tabs(self._port)
            current_keys = set()

            for tab_info in tab_list:
                ws_url = tab_info.get("webSocketDebuggerUrl", "")
                tab_id = tab_info.get("id", "")
                tab_type = tab_info.get("type", "")

                if tab_type not in {"page", ""}:
                    continue
                if not ws_url or not tab_id:
                    continue

                key = self._tab_key(self._port, tab_id)
                current_keys.add(key)

                if key not in self._tabs:
                    await self._connect_tab(tab_info, self._port)
                else:
                    existing = self._tabs[key]
                    existing.url = tab_info.get("url", existing.url)
                    existing.title = tab_info.get("title", existing.title)

            chrome_prefix = f"{self._port}:"
            closed = [key for key in self._tabs if key.startswith(chrome_prefix) and key not in current_keys]
            for key in closed:
                await self._tabs[key].disconnect()
                del self._tabs[key]

            self._last_refresh = time.time()
            logger.debug("[HARNESS] Refreshed: %d tabs", len(self._tabs))
        except Exception as exc:
            logger.error("[HARNESS] Tab refresh failed: %s", exc)

    async def _connect_tab(
        self,
        tab_info: dict,
        port: int,
        default_title: str = "",
    ) -> Optional[Tab]:
        """Connect to a single tab from a CDP target info dict."""
        ws_url = tab_info.get("webSocketDebuggerUrl", "")
        tab_id = tab_info.get("id", "")
        if not ws_url or not tab_id:
            return None

        tab = Tab(
            ws_url=ws_url,
            tab_id=tab_id,
            title=tab_info.get("title", default_title),
            url=tab_info.get("url", ""),
        )
        if await tab.connect():
            self._tabs[self._tab_key(port, tab.tab_id)] = tab
            return tab
        return None

    def _is_still_connected(self, port: Optional[int] = None) -> bool:
        """Check if at least one tab is connected, optionally for one port."""
        if port is None:
            return any(tab._connected for tab in self._tabs.values())
        prefix = f"{port}:"
        return any(key.startswith(prefix) and tab._connected for key, tab in self._tabs.items())

    @staticmethod
    def _tab_key(port: int, tab_id: str) -> str:
        return f"{port}:{tab_id}"


_harness_instance: Optional[BrowserHarness] = None


def get_harness(port: int = _DEFAULT_PORT) -> BrowserHarness:
    """Get or create the global BrowserHarness instance."""
    global _harness_instance
    if _harness_instance is None:
        _harness_instance = BrowserHarness(port=port)
    return _harness_instance
