"""
skills/open_and_type.py

Composite skill: opens an app then types text into it.
Handles "open notepad and type hello" style commands.
Routes native desktop actions through the hardened PCController.
"""

from __future__ import annotations

import logging

from skills.base import SkillBase, SkillResult
from skills.open_app import WEB_APPS
from skills.app_registry import get_app_registry

logger = logging.getLogger("jarvis.skills.open_and_type")


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

        # Check registry for web services and browsers
        _is_web_or_browser = app in WEB_APPS
        if not _is_web_or_browser:
            cap = get_app_registry().get(app)
            _is_web_or_browser = cap is not None and (cap.web_url or cap.search_url or cap.category == "browser")

        if _is_web_or_browser:
            logger.info("'%s' is a web service - redirecting to open_and_search", app)
            from skills.registry import SkillRegistry

            registry = SkillRegistry.instance()
            result = registry.execute(
                "open_and_search",
                {"app": app, "query": text},
                state,
            )
            if result.success:
                return SkillResult(
                    success=True,
                    output=f"Opened {app} and searched for '{text}' (web service - used search instead of typing)",
                )
            return result

        from skills.automation.pc.controller import get_pc

        result_str = get_pc().open_and_type(app, text)
        if "Could not" in result_str:
            return SkillResult(
                success=False,
                output=None,
                error=f"Could not open '{app}': {result_str}",
            )

        state.set_active_app(app)
        return SkillResult(success=True, output=result_str)
