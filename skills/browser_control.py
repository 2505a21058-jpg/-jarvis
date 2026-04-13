import time
from urllib.parse import quote

from memory.context import SESSION_CONTEXT
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


def is_browser_context(app_name: str) -> bool:
    return _normalize(app_name) in BROWSER_APP_NAMES


def determine_search_provider() -> str:
    active_platform = _normalize(SESSION_CONTEXT.get_platform())
    active_app = _normalize(SESSION_CONTEXT.get_app())

    if active_platform == "youtube":
        return "youtube"
    if active_app in {"chrome", "browser", "google"}:
        return "google"
    return "duckduckgo"


def build_search_url(query: str, provider: str = "") -> str:
    resolved_provider = _normalize(provider) or determine_search_provider()
    builder = SEARCH_URLS.get(resolved_provider, SEARCH_URLS["duckduckgo"])
    return builder(str(query or "").strip())


def focus_browser(app_name: str = "") -> bool:
    active_app = _normalize(app_name or SESSION_CONTEXT.get_app()) or "browser"
    title_hints = BROWSER_TITLE_HINTS.get(active_app, BROWSER_TITLE_HINTS["browser"])
    return focus_any_window(title_hints)


def open_url_in_browser(url: str, app_name: str = "") -> tuple[bool, str]:
    target_url = str(url or "").strip()
    if not target_url:
        return False, "empty url"

    try:
        import pyautogui

        if not focus_browser(app_name):
            return False, "browser window not found"

        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.08)
        pyautogui.write(target_url, interval=0)
        pyautogui.press("enter")
        return True, ""
    except Exception as e:
        return False, str(e)


def search_in_browser(query: str, provider: str = "", app_name: str = "") -> tuple[bool, str]:
    url = build_search_url(query, provider=provider)
    return open_url_in_browser(url, app_name=app_name)
