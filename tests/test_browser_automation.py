import asyncio
import subprocess


def test_site_selector_maps_cover_target_sites():
    from skills.automation.browser.selectors import get_site_selectors

    assert 'input#search' in get_site_selectors("https://youtube.com", "search_input")
    assert 'textarea[name="q"]' in get_site_selectors("https://google.com", "search_input")
    assert '[gh="cm"]' in get_site_selectors("https://mail.google.com", "compose")
    assert 'input[data-testid="search-input"]' in get_site_selectors("https://spotify.com", "search_input")


def test_find_element_tries_selectors_until_visible():
    from skills.automation.browser.selectors import find_element

    class Locator:
        def __init__(self, selector, should_fail):
            self.selector = selector
            self.should_fail = should_fail

        @property
        def first(self):
            return self

        async def wait_for(self, state, timeout):
            if self.should_fail:
                raise TimeoutError("not visible")

    class Page:
        def __init__(self):
            self.seen = []

        def locator(self, selector):
            self.seen.append(selector)
            return Locator(selector, should_fail=selector == ".missing")

    page = Page()
    result = asyncio.run(find_element(page, [".missing", ".visible"], timeout=5))

    assert result.selector == ".visible"
    assert page.seen == [".missing", ".visible"]


def test_browser_controller_click_uses_pyautogui_fallback(monkeypatch):
    from skills.automation.browser import controller

    browser = controller.BrowserController()

    class MockPage:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    monkeypatch.setattr(browser, "_safe_page", lambda: _async_return(MockPage()))

    async def no_element(*_args, **_kwargs):
        return None

    monkeypatch.setattr("skills.automation.browser.selectors.find_element", no_element)

    fallback_called = {"value": False}

    async def fallback():
        fallback_called["value"] = True
        return True

    monkeypatch.setattr(browser, "_pyautogui_fallback_click", fallback)

    assert asyncio.run(browser.click([".missing"])) is True
    assert fallback_called["value"] is True


def test_browse_skill_uses_browser_actions_and_os_fallback(monkeypatch):
    from skills.browser import BrowseSkill

    calls = []
    monkeypatch.setattr(
        "skills.automation.browser.actions.navigate_sync",
        lambda url: calls.append(url) or None,
    )

    popen_calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, shell=False: popen_calls.append((args, shell)))

    result = BrowseSkill().execute({"url": "https://example.com"}, {})

    assert result.success is True
    assert calls == ["https://example.com"]
    assert popen_calls == [(["start", "https://example.com"], True)]
    assert "default browser" in result.output


def test_open_and_search_routes_youtube_to_browser_actions(monkeypatch):
    from skills.open_and_search import OpenAndSearchSkill

    monkeypatch.setattr(
        "skills.automation.browser.actions.search_youtube_sync",
        lambda query: f"Searched YouTube for: {query}",
    )

    result = OpenAndSearchSkill().execute({"app": "youtube", "query": "lofi"}, {})

    assert result.success is True
    assert result.output == "Searched YouTube for: lofi"


def test_open_and_browse_uses_browser_actions(monkeypatch):
    from skills.open_and_search import OpenAndBrowseSkill

    calls = []
    monkeypatch.setattr(
        "skills.automation.browser.actions.navigate_sync",
        lambda url: calls.append(url) or f"Opened {url}",
    )

    state = {}
    result = OpenAndBrowseSkill().execute({"app": "chrome", "url": "example.com"}, state)

    assert result.success is True
    assert calls == ["https://example.com"]
    assert state["browser_url"] == "https://example.com"


def test_open_search_and_play_uses_browser_actions_for_youtube(monkeypatch):
    from skills.open_search_and_play import OpenSearchAndPlaySkill

    calls = []
    monkeypatch.setattr(
        "skills.automation.browser.actions.search_youtube_sync",
        lambda query: calls.append(("search", query)) or f"Searched YouTube for: {query}",
    )
    monkeypatch.setattr(
        "skills.automation.browser.actions.click_first_youtube_result_sync",
        lambda: calls.append(("click", None)) or "Clicked first YouTube result",
    )

    result = OpenSearchAndPlaySkill().execute({"app": "youtube", "query": "lofi"}, {})

    assert result.success is True
    assert calls == [("search", "lofi"), ("click", None)]
    assert result.output == "Searched YouTube for: lofi. Clicked first YouTube result"


def test_browser_composite_skills_have_launch_friendly_timeouts():
    from skills.open_and_search import OpenAndBrowseSkill, OpenAndSearchSkill
    from skills.open_search_and_play import OpenSearchAndPlaySkill

    assert OpenAndSearchSkill.timeout_seconds == 45.0
    assert OpenAndBrowseSkill.timeout_seconds == 30.0
    assert OpenSearchAndPlaySkill.timeout_seconds == 60.0


def test_actions_use_gemma_bridge_verification_when_enabled(monkeypatch):
    import os
    from skills.automation.browser import actions

    class Browser:
        async def get_text(self, max_chars=5000):
            return "Example Domain"

        @property
        def current_url(self):
            return "https://example.com"

        async def screenshot(self, path="jarvis_screenshot.png"):
            return True

    calls = []
    monkeypatch.setenv("JARVIS_VISION_VERIFY", "true")
    monkeypatch.setattr(actions, "get_browser", lambda: Browser())
    monkeypatch.setattr(
        "skills.automation.gemma_bridge.verify_browser_action",
        lambda **kwargs: calls.append(kwargs) or True,
        raising=False,
    )

    assert asyncio.run(actions.verify_action("navigate", "https://example.com")) is True
    assert calls and calls[0]["action"] == "navigate"


def test_jarvis_startup_checks_playwright_availability():
    source = open("jarvis.py", encoding="utf-8").read()

    assert "Playwright available" in source
    assert "python -m playwright install chromium" in source


def test_jarvis_prelaunches_chrome_and_keeps_cycle_errors_nonfatal():
    source = open("jarvis.py", encoding="utf-8").read()

    assert "chrome-prelaunch" in source
    assert "ensure_chrome_debug" in source
    assert "Chrome harness ready (profile: jarvis / Profile 3)" in source
    assert "Unhandled error in agent cycle: %s" in source
    assert "exc_info=True" in source
    assert "Please try again." in source


async def _async_return(value):
    return value
