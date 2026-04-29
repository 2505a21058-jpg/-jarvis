from __future__ import annotations

import logging
import re
from urllib.parse import quote
from typing import Any

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ModuleNotFoundError:
    sync_playwright = None

    class PlaywrightTimeoutError(Exception):
        pass

from skills.base import SkillBase, SkillResult
from skills.timeout_utils import TimeoutError as BrowserTimeoutError
from skills.timeout_utils import run_with_timeout
from .search_engine import execute_search, resolve_search_target

logger = logging.getLogger("jarvis.skills.browser")
_playwright = None
_browser = None
_page = None
_browser_context = None
_pages = []
NAVIGATION_WAIT_UNTIL = "domcontentloaded"
NAVIGATION_TIMEOUT_MS = 10000

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
    except:
        pass
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
        _browser_context = _browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )
    _page = _browser_context.new_page()
    _pages.append(_page)
    return _page

class BrowseSkill(SkillBase):
    name = "browse"
    description = "Opens a URL or searches the web"
    timeout_seconds = 15.0

    def _do_browse(self, url: str) -> str:
        task = str(url or "").strip()
        context_app = getattr(self, "_context_app", "")
        timeout_ms = getattr(self, "_timeout_ms", NAVIGATION_TIMEOUT_MS)
        wait_ms = getattr(self, "_wait_ms", 400)
        state = getattr(self, "_state", None)

        try:
            if any(word in task.lower() for word in ["pnr", "train status"]):
                page = get_page()
                pnr = re.search(r"\d{10}", task)
                if not pnr:
                    raise ValueError("Please provide a 10 digit PNR number Sir.")

                pnr_number = pnr.group()
                open_in_tab(
                    page,
                    "https://www.indianrail.gov.in/enquiry/PNR/PnrEnquiry.html?locale=en",
                    timeout_ms=timeout_ms,
                )
                _wait(page, wait_ms)
                try:
                    page.fill("input#inputPnrNo", pnr_number)
                    _wait(page, min(wait_ms, 500))
                    solved = solve_captcha(page, wait_ms=min(wait_ms, 500))
                    if solved:
                        page.click("button#modal1")
                        _wait(page, wait_ms)
                        return f"PNR {pnr_number} status is being fetched Sir."
                    return "PNR entered Sir. Please solve the captcha manually."
                except Exception:
                    return f"PNR page opened Sir. Please enter {pnr_number} manually."

            if any(word in task.lower() for word in ["train", "irctc"]):
                page = get_page()
                open_in_tab(page, "https://www.irctc.co.in", timeout_ms=timeout_ms)
                return "Opened IRCTC Sir. Tell me source, destination and date to proceed."

            resolved = resolve_search_target(task, context_app=context_app, state=state)
            return execute_search(resolved, state=state)
        except PlaywrightTimeoutError as exc:
            raise BrowserTimeoutError("Browser timeout") from exc

    def execute(self, params: dict, state: Any) -> SkillResult:
        url = params.get("url") or params.get("query", "")
        if not url:
            return SkillResult(success=False, output=None, error="No URL or query provided")

        timeout_seconds = max(
            float(params.get("timeout_seconds") or params.get("timeout") or self.timeout_seconds),
            1.0,
        )
        self._context_app = str(params.get("context_app") or _state_get(state, "active_app", "")).strip()
        self._timeout_ms = int(params.get("timeout_ms") or (timeout_seconds * 1000))
        self._wait_ms = int(params.get("wait_ms") or 400)
        self._state = state

        try:
            result = run_with_timeout(
                fn=self._do_browse,
                args=(url,),
                timeout_seconds=timeout_seconds,
            )
            _state_set(state, "active_app", self._context_app or "browser")
            _state_set(state, "active_platform", self._context_app or "browser")
            _state_set(state, "last_action", f"browse:{url}")
            if params.get("url"):
                _state_set(state, "browser_url", str(params.get("url")).strip())
            return SkillResult(success=True, output=result)
        except BrowserTimeoutError:
            logger.error("Browser timed out after %ss for: %s", timeout_seconds, url)
            return SkillResult(
                success=False,
                output=None,
                error=f"Browser timeout after {timeout_seconds}s",
            )
        except Exception as exc:
            logger.error("Browser error: %s", exc)
            return SkillResult(success=False, output=None, error=str(exc))


def browse(task, context_app="", timeout_ms: int = NAVIGATION_TIMEOUT_MS, wait_ms: int = 400, state: Any = None):
    target = str(task or "").strip()
    skill = BrowseSkill()
    timeout_seconds = max(float(timeout_ms) / 1000.0, 1.0)
    result = skill.execute(
        {
            "url": target if target.startswith(("http://", "https://")) else "",
            "query": "" if target.startswith(("http://", "https://")) else target,
            "context_app": context_app,
            "timeout_ms": timeout_ms,
            "wait_ms": wait_ms,
            "timeout_seconds": timeout_seconds,
        },
        state,
    )
    return _tool_result(result.success, result.output, result.error)

def close_browser():
    global _playwright, _browser, _page, _browser_context, _pages
    errors = []

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
