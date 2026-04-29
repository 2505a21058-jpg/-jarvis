from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from .utils.window_focus import focus_any_window


BROWSER_APP_NAMES = {"chrome", "browser", "google"}
BROWSER_TITLE_HINTS = {
    "chrome": ["google chrome", "chrome"],
    "google": ["google chrome", "chrome"],
    "browser": ["google chrome", "chrome", "microsoft edge", "edge", "firefox", "brave"],
}
SEARCH_URLS = {
    "youtube": lambda query: f"https://www.youtube.com/results?search_query={quote(query, safe='')}",
    "google": lambda query: f"https://www.google.com/search?q={quote(query, safe='')}",
    "duckduckgo": lambda query: f"https://duckduckgo.com/?q={quote(query, safe='')}",
}


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _state_get(state: Any, key: str, default: Any = None) -> Any:
    getter = getattr(state, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(state, key, default)


def _state_set(state: Any, key: str, value: Any) -> None:
    if state is None:
        return
    if hasattr(state, key):
        setattr(state, key, value)
    elif isinstance(state, dict):
        state[key] = value


def is_browser_context(app_name: str) -> bool:
    return _normalize(app_name) in BROWSER_APP_NAMES


def determine_search_provider(state: Any = None) -> str:
    active_platform = _normalize(_state_get(state, "active_platform", ""))
    active_app = _normalize(_state_get(state, "active_app", ""))
    configured_engine = _normalize(_state_get(state, "search_engine", ""))

    if active_platform == "youtube":
        return "youtube"
    if configured_engine in SEARCH_URLS:
        return configured_engine
    if active_app in {"chrome", "browser", "google"}:
        return "google"
    return "duckduckgo"


def build_search_url(query: str, provider: str = "", state: Any = None) -> str:
    resolved_provider = _normalize(provider) or determine_search_provider(state=state)
    builder = SEARCH_URLS.get(resolved_provider, SEARCH_URLS["duckduckgo"])
    return builder(str(query or "").strip())


def focus_browser(app_name: str = "", state: Any = None) -> bool:
    active_app = _normalize(app_name or _state_get(state, "active_app", "")) or "browser"
    title_hints = BROWSER_TITLE_HINTS.get(active_app, BROWSER_TITLE_HINTS["browser"])
    return focus_any_window(title_hints)


def open_url_in_browser(url: str, app_name: str = "", state: Any = None) -> tuple[bool, str]:
    target_url = str(url or "").strip()
    if not target_url:
        return False, "empty url"

    try:
        import pyautogui

        if not focus_browser(app_name, state=state):
            return False, "browser window not found"

        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.08)
        pyautogui.write(target_url, interval=0)
        pyautogui.press("enter")
        _state_set(state, "browser_url", target_url)
        return True, ""
    except Exception as e:
        return False, str(e)


def search_in_browser(query: str, provider: str = "", app_name: str = "", state: Any = None) -> tuple[bool, str]:
    url = build_search_url(query, provider=provider, state=state)
    return open_url_in_browser(url, app_name=app_name, state=state)
