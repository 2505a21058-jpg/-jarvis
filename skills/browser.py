from __future__ import annotations

import logging
import re
import webbrowser
from urllib.parse import quote
from typing import Any

from config import env_int, env_str
from skills.base import SkillBase, SkillResult

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ModuleNotFoundError:
    sync_playwright = None

    class PlaywrightTimeoutError(Exception):
        pass

logger = logging.getLogger("jarvis.skills.browser")
_playwright = None
_browser = None
_page = None
_browser_context = None
_pages = []
NAVIGATION_WAIT_UNTIL = "domcontentloaded"
NAVIGATION_TIMEOUT_MS = env_int("JARVIS_BROWSER_NAVIGATION_TIMEOUT_MS", 10000)
BROWSER_VIEWPORT_WIDTH = env_int("JARVIS_BROWSER_VIEWPORT_WIDTH", 1280)
BROWSER_VIEWPORT_HEIGHT = env_int("JARVIS_BROWSER_VIEWPORT_HEIGHT", 720)
BROWSER_USER_AGENT = env_str(
    "JARVIS_BROWSER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
)

BANGS = {
    "youtube": "!yt",
    "amazon": "!amz",
    "github": "!gh",
    "maps": "!maps",
    "google maps": "!maps",
    "reddit": "!reddit",
    "wikipedia": "!w",
    "wiki": "!w",
    "stackoverflow": "!so",
    "stack overflow": "!so",
    "twitter": "!twitter",
    "instagram": "!instagram",
    "flipkart": "!flipkart",
    "netflix": "!netflix",
    "spotify": "!spotify",
    "translate": "!translate",
    "news": "!gnews",
    "images": "!gi",
    "google": "!g",
}

SITE_HINTS = {
    "youtube", "github", "amazon", "reddit", "wikipedia", "stackoverflow",
    "twitter", "instagram", "flipkart", "netflix", "spotify", "google", "irctc"
}

KNOWN_SERVICE_URLS = {
    "google maps": "https://www.google.com/maps",
    "maps": "https://www.google.com/maps",
    "docs": "https://docs.google.com",
    "google docs": "https://docs.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
}

BROWSE_PREFIXES = ("open ", "search for ", "search ", "find ", "look up ", "show me ")


def _tool_result(success: bool, output=None, error: str | None = None):
    return {
        "success": bool(success),
        "output": output,
        "error": error,
    }


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    getter = getattr(state, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(state, key, default)


def _state_set(state: Any, key: str, value: Any) -> None:
    if hasattr(state, key):
        setattr(state, key, value)
        return
    if isinstance(state, dict):
        state[key] = value

def get_bang(task):
    task_lower = task.lower()
    for key, bang in BANGS.items():
        if key in task_lower:
            query = task_lower.replace(key, "").replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
            return bang, query
    query = task_lower.replace("search", "").replace(" for ", " ").replace(" on ", " ").strip()
    return None, query

def build_duckduckgo_url(query):
    return f"https://duckduckgo.com/?q={quote(str(query).strip(), safe='')}"


def strip_browse_prefix(task):
    text = task.strip()
    lowered = text.lower()
    for prefix in BROWSE_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def resolve_browse_target(task):
    text = strip_browse_prefix(task)
    lowered = text.lower().strip(" .?!")

    if not lowered:
        return "https://duckduckgo.com", "Opened browser Sir.", ""

    if text.startswith(("http://", "https://")):
        return text, f"Opened {text} Sir.", lowered

    if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", lowered):
        url = f"https://{lowered}"
        return url, f"Opened {url} Sir.", lowered

    if lowered in KNOWN_SERVICE_URLS:
        url = KNOWN_SERVICE_URLS[lowered]
        return url, f"Opened {url} Sir.", lowered

    url = build_duckduckgo_url(text)
    return url, f"Searched for {text} Sir.", text


def _wait(page, wait_ms: int) -> None:
    if wait_ms > 0:
        page.wait_for_timeout(wait_ms)


def solve_captcha(page, wait_ms: int = 500):
    try:
        captcha_text = page.inner_text("label[for=inputCaptcha]")
        numbers = re.findall(r"\d+", captcha_text)
        if len(numbers) >= 2:
            if "+" in captcha_text:
                answer = int(numbers[0]) + int(numbers[1])
            elif "-" in captcha_text:
                answer = int(numbers[0]) - int(numbers[1])
            elif "*" in captcha_text:
                answer = int(numbers[0]) * int(numbers[1])
            else:
                answer = int(numbers[0]) + int(numbers[1])
            page.fill("input#inputCaptcha", str(answer))
            _wait(page, wait_ms)
            return True
    except Exception as exc:
        # Captcha solver failures are logged so manual fallback is explainable.
        logger.debug("Captcha auto-solve skipped: %s", exc)
    return False


def open_in_tab(page, url, timeout_ms: int = NAVIGATION_TIMEOUT_MS):
    page.goto(url, wait_until=NAVIGATION_WAIT_UNTIL, timeout=timeout_ms)
    page.bring_to_front()

def get_page():
    global _playwright, _browser, _page, _browser_context, _pages
    if sync_playwright is None:
        raise RuntimeError("playwright is not installed")
    if _playwright is None:
        _playwright = sync_playwright().start()
    if _browser is None:
        _browser = _playwright.firefox.launch(headless=False)
    if _browser_context is None:
        # Browser viewport/user-agent are configurable for sites that react to device profiles.
        _browser_context = _browser.new_context(
            viewport={"width": BROWSER_VIEWPORT_WIDTH, "height": BROWSER_VIEWPORT_HEIGHT},
            user_agent=BROWSER_USER_AGENT,
        )
    _page = _browser_context.new_page()
    _pages.append(_page)
    return _page



def close_browser():
    global _playwright, _browser, _page, _browser_context, _pages
    errors = []

    try:
        from skills.automation.browser import controller as browser_controller
        from skills.automation.browser.actions import _run_async

        if browser_controller._browser_instance is not None:
            _run_async(browser_controller._browser_instance.close())
    except Exception as e:
        errors.append(f"browser controller close failed: {e}")

    pages = list(_pages)
    context = _browser_context
    browser = _browser
    playwright = _playwright

    _page = None
    _browser_context = None
    _browser = None
    _playwright = None
    _pages = []

    for page in pages:
        try:
            if not page.is_closed():
                page.close()
        except Exception as e:
            errors.append(f"page close failed: {e}")

    if context is not None:
        try:
            context.close()
        except Exception as e:
            errors.append(f"context close failed: {e}")

    if browser is not None:
        try:
            browser.close()
        except Exception as e:
            errors.append(f"browser close failed: {e}")

    if playwright is not None:
        try:
            playwright.stop()
        except Exception as e:
            errors.append(f"playwright stop failed: {e}")

    return errors


class BrowseSkill(SkillBase):
    name = "browse"
    description = "Opens a URL or searches the web in the browser"
    timeout_seconds = 45.0

    def execute(self, params: dict, state) -> SkillResult:
        target = str(
            params.get("url")
            or params.get("query")
            or params.get("target")
            or params.get("app")
            or ""
        ).strip()
        if not target:
            return SkillResult(success=False, output=None, error="No URL or query provided")

        url, message, _ = resolve_browse_target(target)
        try:
            from skills.automation.browser.actions import navigate_sync

            result = navigate_sync(url)
            if result and "failed" in str(result).lower():
                raise RuntimeError(str(result))
        except Exception as exc:
            logger.debug("Browser automation unavailable for %s: %s", url, exc)
            webbrowser.open(url)

        _state_set(state, "browser_url", url)
        _state_set(state, "active_app", "browser")
        return SkillResult(success=True, output=message)
