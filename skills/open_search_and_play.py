"""
skills/open_search_and_play.py

Composite skill: opens an app, searches, then clicks the first result.
Production browser automation is handled by skills.automation.browser.
"""

import logging
from urllib.parse import quote_plus

from skills.base import SkillBase, SkillResult
from skills.app_registry import get_app_registry


logger = logging.getLogger("jarvis.skills.open_search_and_play")


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


class OpenSearchAndPlaySkill(SkillBase):
    name = "open_search_and_play"
    description = "Opens an app, searches for content, and opens the first result"
    timeout_seconds = 60.0

    def execute(self, params: dict, state) -> SkillResult:
        app = params.get("app", "").strip().lower()
        query = params.get("query", "").strip()

        if not app or not query:
            return SkillResult(
                success=False,
                output=None,
                error="Need both 'app' and 'query'",
            )

        registry = get_app_registry()
        canonical = registry.resolve(app)
        cap = registry.get(canonical)

        if cap and cap.supports_play:
            if "youtube" in canonical:
                from skills.automation.browser.actions import (
                    click_first_youtube_result_sync,
                    search_youtube_sync,
                )
                search_result = search_youtube_sync(query)
                play_result = click_first_youtube_result_sync()
            else:
                from skills.automation.browser.actions import (
                    navigate_sync, search_in_page_sync, click_sync,
                )
                url = cap.web_url or f"https://www.{canonical}.com"
                navigate_sync(url)
                search_in_page_sync(query)
                play_result = click_sync("first result")
                search_result = f"Searched {cap.display_name} for: {query}"

            search_url = registry.search_url_for(canonical, query) or ""
            _set_browser_state(state, search_url)
            play_ok = play_result and not any(
                word in play_result.lower() for word in ["could not", "failed", "not found"]
            )
            if play_ok:
                logger.info("Searched %s and clicked first result for: %s", cap.display_name, query)
                return SkillResult(success=True, output=f"{search_result}. {play_result}")
            logger.warning("Play step failed for %s: %s", cap.display_name, play_result)
            return SkillResult(success=False, output=f"{search_result}", error=play_result)

        if cap and cap.supports_search and cap.search_url:
            from skills.automation.browser.actions import navigate_sync, search_in_page_sync
            url = cap.web_url or cap.search_url.replace("{query}", quote_plus(query))
            navigate_sync(url)
            search_in_page_sync(query)
            search_url = registry.search_url_for(canonical, query) or ""
            _set_browser_state(state, search_url)
            logger.info("Searched %s for: %s", cap.display_name, query)
            return SkillResult(success=True, output=f"Searched {cap.display_name} for: {query}")

        # Fallback: treat as generic browser search
        from skills.automation.browser.actions import navigate_sync
        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        navigate_sync(search_url)
        _set_browser_state(state, search_url)
        logger.info("Searched Google for: %s", query)
        return SkillResult(success=True, output=f"Searched Google for: {query}")
