"""
skills/open_and_type.py

Composite skill: opens an app then types text into it.
Handles "open notepad and type hello" style commands.
Waits for app to be ready before typing.
"""

import logging
import time

from skills.base import SkillBase, SkillResult
from skills.open_and_search import BROWSER_NAMES, WEB_APPS

logger = logging.getLogger("jarvis.skills.open_and_type")

APP_LAUNCH_WAIT = {
    "notepad": 1.5,
    "notepad++": 2.0,
    "wordpad": 2.0,
    "word": 3.0,
    "excel": 3.0,
    "code": 3.0,
    "vscode": 3.0,
    "cursor": 3.0,
    "terminal": 2.0,
    "cmd": 1.5,
    "default": 2.0,
}


class OpenAndTypeSkill(SkillBase):
    name = "open_and_type"
    description = "Opens an application then types specified text into it"
    timeout_seconds = 15.0

    def execute(self, params: dict, state) -> SkillResult:
        app = params.get("app", "").strip().lower()
        text = params.get("text", "").strip()

        if not app:
            return SkillResult(success=False, output=None, error="No app name provided")
        if not text:
            return SkillResult(success=False, output=None, error="No text to type")

        app_lower = app.lower()

        # Web services and browser searches should use URL search flows, not typing automation.
        if app_lower in WEB_APPS or app_lower in BROWSER_NAMES:
            logger.info("'%s' is a web service - redirecting to open_and_search", app)
            from skills.registry import SkillRegistry

            registry = SkillRegistry.instance()
            result = registry.execute(
                "open_and_search",
                {"app": app_lower, "query": text},
                state,
            )
            if result.success:
                return SkillResult(
                    success=True,
                    output=f"Opened {app} and searched for '{text}' (web service - used search instead of typing)",
                )
            return result

        import platform
        if platform.system() == "Windows":
            # Try reliable pywinauto method first
            try:
                from skills.gui_automate import _type_into_app
                success, message = _type_into_app(app, text)
                if success:
                    state.set_active_app(app)
                    return SkillResult(success=True, output=message)
                logger.warning(f"pywinauto method failed: {message}, trying fallback")
            except Exception as e:
                logger.warning(f"pywinauto unavailable: {e}, using fallback")

        # Fallback: original sleep-based approach
        from skills.registry import SkillRegistry
        registry = SkillRegistry.instance()
        open_result = registry.execute("open_app", {"app": app}, state)
        if not open_result.success:
            return SkillResult(success=False, output=None,
                              error=f"Could not open '{app}': {open_result.error}")

        wait_time = APP_LAUNCH_WAIT.get(app, APP_LAUNCH_WAIT["default"])
        time.sleep(wait_time)
        state.set_active_app(app)

        type_result = registry.execute("type_text", {"text": text}, state)
        if not type_result.success:
            return SkillResult(success=False, output=None,
                              error=f"Opened '{app}' but typing failed: {type_result.error}")

        return SkillResult(success=True, output=f"Opened {app} and typed: {text[:80]}")
