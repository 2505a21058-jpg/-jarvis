"""
skills/open_search_and_play.py

Composite skill: opens an app, searches, then clicks the first result.
Handles "open youtube, search X and play first song" pattern.

Uses webbrowser for search + optional vision click for first result.
If vision unavailable, opens search results and informs user.
"""

import logging
from urllib.parse import quote_plus

from config import FIRST_RESULT_CLICK_X_RATIO, FIRST_RESULT_CLICK_Y_RATIO, FIRST_RESULT_WAIT_SECONDS
from skills.base import SkillBase, SkillResult
from skills.open_and_search import SEARCH_URL_TEMPLATES


logger = logging.getLogger("jarvis.skills.open_search_and_play")


class OpenSearchAndPlaySkill(SkillBase):
    name = "open_search_and_play"
    description = "Opens an app, searches for content, and opens the first result"
    timeout_seconds = 15.0

    def execute(self, params: dict, state) -> SkillResult:
        app = params.get("app", "").strip().lower()
        query = params.get("query", "").strip()

        if not app or not query:
            return SkillResult(
                success=False,
                output=None,
                error="Need both 'app' and 'query'",
            )

        encoded = quote_plus(query)

        if app in SEARCH_URL_TEMPLATES:
            # Reuse shared search templates so this composite skill stays in sync with open_and_search.
            url = SEARCH_URL_TEMPLATES[app].format(query=encoded)
        else:
            # Google fallback also reuses the shared template to avoid duplicating search URLs.
            url = SEARCH_URL_TEMPLATES["google"].format(query=f"{encoded}+{app}")

        try:
            import webbrowser

            webbrowser.open(url)
            if state is not None:
                if hasattr(state, "browser_url"):
                    state.browser_url = url
                if hasattr(state, "set_active_app"):
                    state.set_active_app("browser")
            logger.info("Opened %s search for: %s", app, query)
        except Exception as exc:
            return SkillResult(success=False, output=None, error=str(exc))

        import time

        time.sleep(FIRST_RESULT_WAIT_SECONDS)

        vision_clicked = False
        try:
            from agent.screen_verify import _ask_vision_model, _take_screenshot

            screenshot = _take_screenshot()
            if screenshot:
                answer = _ask_vision_model(
                    screenshot,
                    f"I'm looking at search results for '{query}' on {app}. "
                    "Is the first result/video/song visible? "
                    "Answer yes or no only.",
                )
                if answer and answer.lower().startswith("yes"):
                    try:
                        import pyautogui
                        import pygetwindow as gw

                        wins = gw.getWindowsWithTitle("")
                        if wins:
                            w = wins[0]
                            # Fallback click ratios are configurable until full coordinate vision lands.
                            click_x = w.left + int(w.width * FIRST_RESULT_CLICK_X_RATIO)
                            click_y = w.top + int(w.height * FIRST_RESULT_CLICK_Y_RATIO)
                            pyautogui.click(click_x, click_y)
                            vision_clicked = True
                            logger.info("Clicked first result via vision guidance")
                    except Exception as exc:
                        logger.debug("Vision click failed: %s", exc)
        except Exception as exc:
            logger.debug("Vision step failed: %s", exc)

        if vision_clicked:
            return SkillResult(
                success=True,
                output=f"Opened {app}, searched for '{query}', and clicked the first result.",
            )

        return SkillResult(
            success=True,
            output=(
                f"Opened {app} and searched for '{query}'.\n"
                "The search results are open - click the first result to play it.\n"
                "(Auto-click requires vision model. Enable with JARVIS_VISION_VERIFY=true)"
            ),
        )
