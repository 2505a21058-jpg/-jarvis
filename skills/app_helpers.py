"""
skills/app_helpers.py

Shared helpers for all template skills.
- Browser apps (youtube, google, etc.): CDP via Playwright → existing Chrome (shared across steps)
- Fresh Playwright Chrome as fallback
- Native apps: pyautogui
- Select/click via RawVision + HandsController
"""

from __future__ import annotations

import logging
import subprocess
import time
import webbrowser
from urllib.parse import quote_plus

logger = logging.getLogger("jarvis.app_helpers")

_ALIASES = {
    "notes": "notepad",
    "calc": "calculator",
    "word": "winword",
    "excel": "excel",
    "ppt": "powerpnt",
    "powerpoint": "powerpnt",
    "vs": "Code",
    "vscode": "Code",
    "code": "Code",
    "chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "cmd": "cmd",
    "terminal": "wt",
    "paint": "mspaint",
    "snipping tool": "SnippingTool",
}

_URL_APPS = {
    "youtube": "https://youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://google.com",
    "maps": "https://maps.google.com",
    "drive": "https://drive.google.com",
    "github": "https://github.com",
    "twitter": "https://twitter.com",
    "reddit": "https://reddit.com",
    "spotify": "https://open.spotify.com",
    "netflix": "https://netflix.com",
    "amazon": "https://amazon.com",
    "flipkart": "https://flipkart.com",
    "instagram": "https://instagram.com",
}

_SEARCH_URLS = {
    "youtube": lambda q: f"https://www.youtube.com/results?search_query={quote_plus(str(q))}",
    "google":  lambda q: f"https://www.google.com/search?q={quote_plus(str(q))}",
}

_CDP_PORT = 9222


def resolve_app(app: str) -> str:
    lowered = app.strip().lower()
    return _ALIASES.get(lowered, app)


def is_url_app(app: str) -> bool:
    return app.strip().lower() in _URL_APPS


def get_url_for(app: str) -> str:
    return _URL_APPS.get(app.strip().lower(), "")


def _looks_like_url(target: str) -> bool:
    text = str(target or "").strip().lower()
    return text.startswith(("http://", "https://")) or "." in text and " " not in text


def _normalize_url(target: str) -> str:
    text = str(target or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    return "https://" + text


def _get_page(context):
    """Get or create a shared Playwright page from StepRunnerSkill context.
    
    Attempts CDP → existing Chrome first (fast), falls back to fresh Playwright Chrome.
    """
    if hasattr(context, '_page') and context._page is not None:
        return context._page

    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    err = None

    # Try CDP → existing Chrome (fast, ~100ms)
    try:
        browser = p.chromium.connect_over_cdp(f"http://localhost:{_CDP_PORT}")
        page = browser.contexts[0].new_page()
        context._playwright = p
        context._browser = browser
        context._page = page
        return page
    except Exception as exc:
        err = exc
        logger.debug("[CDP] connect failed, launching fresh Chrome: %s", exc)

    # Fallback: launch fresh Playwright Chrome (slower, ~3s)
    try:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        context._playwright = p
        context._browser = browser
        context._page = page
        return page
    except Exception as exc2:
        p.stop()
        raise RuntimeError(f"Playwright unavailable: {err}, {exc2}")


def launch_and_prep(app: str, context=None) -> bool:
    target = str(app or "").strip()
    if not target:
        return False
    if is_url_app(target) or _looks_like_url(target):
        url = get_url_for(target) if is_url_app(target) else _normalize_url(target)
        try:
            page = _get_page(context)
            page.goto(url, wait_until="commit", timeout=15000)
            return True
        except Exception as exc:
            logger.warning("[Playwright] launch %s failed: %s", target, exc)
            webbrowser.open(url)
            time.sleep(1.0)
            return True
    resolved = resolve_app(target)
    subprocess.Popen([resolved], shell=False)
    time.sleep(1.0)
    return True


def step_search(query: str, app: str = "", context=None) -> bool:
    lowered = app.strip().lower()
    builder = _SEARCH_URLS.get(lowered)
    if builder:
        url = builder(query)
        try:
            page = _get_page(context)
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            return True
        except Exception as exc:
            logger.warning("[Playwright] search goto %s failed: %s", url, exc)
    import pyautogui
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    pyautogui.write(query, interval=0.01)
    pyautogui.press("enter")
    time.sleep(1.5)
    return True


def step_play_first(query: str = "", app: str = "", context=None) -> bool:
    try:
        page = _get_page(context)
        page.wait_for_selector("ytd-video-renderer a#video-title", timeout=5000)
        page.click("ytd-video-renderer a#video-title")
        return True
    except Exception:
        pass
    if query and app:
        lowered = app.strip().lower()
        builder = _SEARCH_URLS.get(lowered)
        if builder:
            url = builder(query)
            try:
                page = _get_page(context)
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_selector("ytd-video-renderer a#video-title", timeout=5000)
                page.click("ytd-video-renderer a#video-title")
                return True
            except Exception:
                pass
    import pyautogui
    time.sleep(2.0)
    for _ in range(5):
        pyautogui.press("tab")
        time.sleep(0.15)
    pyautogui.press("enter")
    return True


def step_select(target: str) -> bool:
    target = str(target or "").strip()
    if not target:
        return False
    from rawvision.output.schema import ElementRole
    from rawvision import RawVision
    ctx = RawVision().capture()
    element = ctx.find(name=target) or ctx.find(name=target, role=ElementRole.BUTTON)
    if element:
        from agent.hands import get_hands
        return get_hands().click(element).success
    import pyautogui
    pyautogui.click()
    return True


def step_type_text(text: str) -> bool:
    import pyautogui
    pyautogui.write(text, interval=0.01)
    return True


def step_shortcut(keys: str) -> bool:
    import pyautogui
    pyautogui.hotkey(*keys.split("+"))
    return True


def step_scroll(direction: str = "down") -> bool:
    import pyautogui
    pyautogui.scroll(-3 if direction == "down" else 3)
    return True


def step_wait(seconds: int = 1) -> bool:
    time.sleep(seconds)
    return True


def step_close() -> bool:
    import pyautogui
    pyautogui.hotkey("alt", "f4")
    return True


STEP_FUNCS = {
    "open": lambda p, ctx=None: launch_and_prep(p.get("app") or p.get("url") or p.get("target", ""), ctx),
    "search": lambda p, ctx=None: step_search(p.get("query") or p.get("text") or p.get("topic", ""), p.get("app", ""), ctx),
    "select": lambda p, ctx=None: step_select(p.get("target") or p.get("name") or p.get("element", "")),
    "type": lambda p, ctx=None: step_type_text(p.get("text", "")),
    "play": lambda p, ctx=None: step_play_first(p.get("query", ""), p.get("app", ""), ctx),
    "scroll": lambda p, ctx=None: step_scroll(p.get("direction", "down")),
    "shortcut": lambda p, ctx=None: step_shortcut(p.get("keys", p.get("combo", ""))),
    "wait": lambda p, ctx=None: step_wait(int(p.get("seconds", 1))),
    "close": lambda p, ctx=None: step_close(),
    "tab": lambda p, ctx=None: step_shortcut("ctrl+t"),
}
