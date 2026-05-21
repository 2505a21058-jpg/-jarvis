import logging
import time

from skills.base import SkillBase, SkillResult
from skills.open_app import WEB_APPS
from skills.app_registry import get_app_registry


logger = logging.getLogger("jarvis.skills.open_and_search")


def _set_browser_state(state, url: str) -> None:
    if state is None:
        return
    if hasattr(state, "browser_url"):
        state.browser_url = url
    elif isinstance(state, dict):
        state["browser_url"] = url

    if hasattr(state, "set_active_app"):
        state.set_active_app("browser")
    elif hasattr(state, "active_app"):
        state.active_app = "browser"
    elif isinstance(state, dict):
        state["active_app"] = "browser"


class OpenAndSearchSkill(SkillBase):
    name = "open_and_search"
    description = "Opens an app or website and searches for something within it"
    timeout_seconds = 45.0

    def execute(self, params: dict, state) -> SkillResult:
        app = params.get("app", "").strip().lower()
        query = params.get("query", "").strip()

        if not app:
            return SkillResult(
                success=False,
                output=None,
                error="No app specified",
            )
        if not query:
            return SkillResult(
                success=False,
                output=None,
                error="No search query provided",
            )

        registry = get_app_registry()
        canonical = registry.resolve(app)
        cap = registry.get(canonical)

        # Try Hero first for YouTube (better bot evasion)
        if cap and "youtube" in canonical:
            try:
                from skills.automation.hero.actions import search_youtube
                from skills.automation.hero.setup import is_hero_available
                if is_hero_available():
                    result = search_youtube(query)
                    url = registry.search_url_for(canonical, query) or ""
                    _set_browser_state(state, url)
                    return SkillResult(
                        success=bool(result),
                        output=result or "Could not search YouTube"
                    )
            except Exception as e:
                logger.debug("[SKILL] Hero failed, using Playwright: %s", e)

            from skills.automation.browser.actions import search_youtube_sync
            result = search_youtube_sync(query)
            url = registry.search_url_for(canonical, query) or ""
            _set_browser_state(state, url)
            return SkillResult(success=bool(result), output=result or "Could not search YouTube")

        # Browser or search-engine: navigate to search page
        if cap and (cap.category == "browser" or cap.search_url):
            from skills.automation.browser.actions import navigate_sync, search_in_page_sync
            target_url = cap.search_url.replace("{query}", query) if cap and cap.search_url else f"https://www.google.com/search?q={query}"
            navigate_sync(cap.web_url or "https://www.google.com")
            result = search_in_page_sync(query, cap.name)
            search_url = registry.search_url_for(canonical, query) or ""
            _set_browser_state(state, search_url)
            return SkillResult(success=bool(result), output=result or f"Could not search {cap.display_name}")

        # Fallback: open app then do generic browser search
        from skills.automation.browser.actions import navigate_sync, search_in_page_sync
        logger.info("App '%s' not in registry — falling back to Google search", app)
        navigate_sync("https://www.google.com")
        result = search_in_page_sync(query, "google.com")
        _set_browser_state(state, f"https://www.google.com/search?q={query}")
        return SkillResult(success=bool(result), output=result or "Could not search Google")


class OpenAndBrowseSkill(SkillBase):
    name = "open_and_browse"
    description = "Opens an app and navigates to a specific URL"
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        url = params.get("url", "").strip()

        if not url:
            return SkillResult(success=False, output=None, error="No URL specified")

        if not url.startswith("http"):
            url = "https://" + url

        from skills.automation.browser.actions import navigate_sync

        result = navigate_sync(url)
        if result and "Failed" not in result:
            _set_browser_state(state, url)
            return SkillResult(success=True, output=result)

        try:
            import subprocess

            subprocess.Popen(["start", url], shell=True)
            _set_browser_state(state, url)
            return SkillResult(
                success=True,
                output=f"Opened {url} in default browser",
            )
        except Exception as exc:
            return SkillResult(success=False, output=None, error=str(exc))
