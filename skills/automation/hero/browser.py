"""
skills/automation/hero/browser.py

Hero browser controller.
Drop-in replacement for BrowserController for web automation.

Hero advantages over raw Playwright/CDP:
- Human emulation (mouse curves, natural typing)
- Bot detection evasion (Cloudflare, reCAPTCHA friendly)
- Intelligent waiting (no fixed sleep())
- Shadow DOM support
- Resource blocking built-in
- Designed specifically for automation
"""

from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Optional

logger = logging.getLogger("jarvis.hero.browser")

_HERO_PORT = 1818
_HERO_BASE = f"http://localhost:{_HERO_PORT}"


class HeroBrowser:
    """
    Python client for Hero (Ulixee) automation.
    Connects to the Hero Core Node.js server.
    """

    def __init__(self):
        self._session_id: Optional[str] = None

    def _post(self, endpoint: str,
              data: dict) -> Optional[dict]:
        """POST to Hero Core API."""
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(
                f"{_HERO_BASE}/{endpoint}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.error("[HERO] POST /%s failed: %s", endpoint, e)
            return None

    def navigate(self, url: str) -> bool:
        """Navigate to URL with human emulation."""
        result = self._post("navigate", {
            "url": url,
            "waitForLoad": True
        })
        if result and result.get("success"):
            logger.info("[HERO] Navigated to %s", url)
            return True
        return False

    def click(self, selector: str = "",
              text: str = "") -> bool:
        """
        Click element by CSS selector or text.
        Hero uses human-like mouse movement.
        """
        payload = {}
        if selector:
            payload["selector"] = selector
        if text:
            payload["text"] = text

        result = self._post("click", payload)
        return bool(result and result.get("success"))

    def type_text(self, text: str,
                  selector: str = "") -> bool:
        """
        Type text with human-like timing.
        Hero handles timing automatically.
        """
        payload = {"text": text}
        if selector:
            payload["selector"] = selector

        result = self._post("type", payload)
        return bool(result and result.get("success"))

    def get_text(self, selector: str = "body") -> str:
        """Get visible text from element."""
        result = self._post("getText", {
            "selector": selector
        })
        return result.get("text", "") if result else ""

    def get_url(self) -> str:
        """Get current URL."""
        result = self._post("getUrl", {})
        return result.get("url", "") if result else ""

    def wait_for(self, selector: str,
                 timeout_ms: int = 8000) -> bool:
        """Wait for element to appear."""
        result = self._post("waitFor", {
            "selector": selector,
            "timeoutMs": timeout_ms
        })
        return bool(result and result.get("success"))

    def screenshot_b64(self) -> Optional[str]:
        """Take screenshot, return base64."""
        result = self._post("screenshot", {})
        return result.get("data") if result else None

    def evaluate(self, js: str) -> Any:
        """Execute JavaScript."""
        result = self._post("evaluate", {"js": js})
        return result.get("result") if result else None

    def fetch(self, url: str, method: str = "GET",
              body: Optional[dict] = None) -> Optional[dict]:
        """
        HTTP request as the page.
        Uses page cookies/auth — same as CDP fetch.
        """
        result = self._post("fetch", {
            "url": url,
            "method": method,
            "body": body
        })
        return result

    def close(self):
        """Close browser session."""
        self._post("close", {})
        self._session_id = None


_hero_instance: Optional[HeroBrowser] = None


def get_hero() -> HeroBrowser:
    global _hero_instance
    if _hero_instance is None:
        _hero_instance = HeroBrowser()
    return _hero_instance
