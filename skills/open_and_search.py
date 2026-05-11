"""
skills/open_and_search.py

Composite skill: opens an app or website then performs a search.
Handles "open youtube and search for X" style commands.
"""

import logging
import time
from urllib.parse import quote_plus

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.open_and_search")


# Web services with direct search URL templates
SEARCH_URL_TEMPLATES = {
    "youtube":       "https://www.youtube.com/results?search_query={query}",
    "google":        "https://www.google.com/search?q={query}",
    "gmail":         "https://mail.google.com/mail/u/0/#search/{query}",
    "github":        "https://github.com/search?q={query}",
    "reddit":        "https://www.reddit.com/search/?q={query}",
    "twitter":       "https://twitter.com/search?q={query}",
    "x":             "https://x.com/search?q={query}",
    "linkedin":      "https://www.linkedin.com/search/results/all/?keywords={query}",
    "amazon":        "https://www.amazon.com/s?k={query}",
    "netflix":       "https://www.netflix.com/search?q={query}",
    "spotify":       "https://open.spotify.com/search/{query}",
    "bing":          "https://www.bing.com/search?q={query}",
    "duckduckgo":    "https://duckduckgo.com/?q={query}",
    "wikipedia":     "https://en.wikipedia.org/w/index.php?search={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "maps":          "https://www.google.com/maps/search/{query}",
    "google maps":   "https://www.google.com/maps/search/{query}",
    "news":          "https://news.google.com/search?q={query}",
    "google news":   "https://news.google.com/search?q={query}",
    "imdb":          "https://www.imdb.com/find?q={query}",
    "pinterest":     "https://www.pinterest.com/search/pins/?q={query}",
    "ebay":          "https://www.ebay.com/sch/i.html?_nkw={query}",
    "flipkart":      "https://www.flipkart.com/search?q={query}",
}

# Browser names - when user says "open chrome and search for X"
# they mean "search Google in Chrome", not "search chrome.com".
BROWSER_NAMES = {
    "chrome",
    "firefox",
    "edge",
    "safari",
    "opera",
    "brave",
    "browser",
    "web browser",
    "internet explorer",
    "ie",
}


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
    timeout_seconds = 10.0

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

        encoded_query = quote_plus(query)

        if app in BROWSER_NAMES:
            url = f"https://www.google.com/search?q={encoded_query}"
            logger.info("'%s' is a browser - searching Google for: %s", app, query)
        elif app in SEARCH_URL_TEMPLATES:
            url = SEARCH_URL_TEMPLATES[app].format(query=encoded_query)
            logger.info("Using search template for '%s': %s", app, query)
        else:
            if " " not in app and len(app) < 20:
                url = f"https://www.google.com/search?q={encoded_query}+{app}"
                logger.info("No template for '%s' - searching Google for: %s %s", app, query, app)
            else:
                url = f"https://www.google.com/search?q={encoded_query}"
                logger.info("Falling back to Google search for: %s", query)

        try:
            import webbrowser

            webbrowser.open(url)
            _set_browser_state(state, url)
            return SkillResult(
                success=True,
                output=f"Opened {app} and searched for '{query}'",
            )
        except Exception as exc:
            logger.error("OpenAndSearch failed: %s", exc)
            return SkillResult(success=False, output=None, error=str(exc))


class OpenAndBrowseSkill(SkillBase):
    name = "open_and_browse"
    description = "Opens an app and navigates to a specific URL"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        app = params.get("app", "").strip().lower()
        url = params.get("url", "").strip()

        if not url:
            return SkillResult(success=False, output=None, error="No URL specified")

        if not url.startswith("http"):
            url = "https://" + url

        try:
            import webbrowser

            webbrowser.open(url)
            _set_browser_state(state, url)
            return SkillResult(
                success=True,
                output=f"Opened {url}",
            )
        except Exception as exc:
            return SkillResult(success=False, output=None, error=str(exc))
