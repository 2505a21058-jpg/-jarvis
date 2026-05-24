"""Compatibility GUI automation skill backed by template step helpers."""

from __future__ import annotations

import logging

from skills.app_helpers import launch_and_prep, step_select, step_shortcut, step_type_text
from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.gui_automate")


def _find_and_click(element_name: str, app_name: str | None = None, timeout: float | None = None) -> tuple[bool, str]:
    _ = app_name, timeout
    target = str(element_name or "").strip()
    if not target:
        return False, "No element name to click"
    ok = step_select(target)
    return ok, f"Clicked '{target}'" if ok else f"Element '{target}' not found"


def _type_active(text: str) -> tuple[bool, str]:
    cleaned = str(text or "")
    if not cleaned:
        return False, "No text provided"
    ok = step_type_text(cleaned)
    return ok, f"Typed {len(cleaned)} characters" if ok else "Typing failed"


def _press_key_sequence(sequence: str) -> tuple[bool, str]:
    keys = str(sequence or "").strip()
    if not keys:
        return False, "No key sequence provided"
    ok = step_shortcut(keys)
    return ok, f"Pressed {keys}" if ok else f"Could not press {keys}"


def _get_active_window_title() -> str:
    try:
        import win32gui

        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception as exc:
        logger.debug("Active window lookup failed: %s", exc)
        return ""


class GUIAutomateSkill(SkillBase):
    name = "gui_automate"
    description = "Runs GUI actions such as click, type, hotkey, focus, and active-window checks"
    timeout_seconds = 20.0

    def execute(self, params: dict, state) -> SkillResult:
        _ = state
        action = str(params.get("action") or "").strip().lower()

        if action == "click":
            element = str(params.get("element") or params.get("target") or "").strip()
            app = str(params.get("app") or "").strip() or None
            ok, message = _find_and_click(element, app)
            return SkillResult(success=ok, output=message if ok else None, error=None if ok else message)

        if action in {"press", "hotkey"}:
            keys = str(params.get("keys") or params.get("key") or params.get("element") or "").strip()
            ok, message = _press_key_sequence(keys)
            return SkillResult(success=ok, output=message if ok else None, error=None if ok else message)

        if action in {"type_active", "type"}:
            app = str(params.get("app") or "").strip()
            text = str(params.get("text") or "").strip()
            if action == "type" and app and not launch_and_prep(app):
                return SkillResult(success=False, output=None, error=f"Could not open '{app}'")
            ok, message = _type_active(text)
            return SkillResult(success=ok, output=message if ok else None, error=None if ok else message)

        if action == "focus":
            app = str(params.get("app") or "").strip()
            if not app:
                return SkillResult(success=False, output=None, error="No app to focus")
            ok = launch_and_prep(app)
            return SkillResult(success=ok, output=f"Focused {app}" if ok else None, error=None if ok else f"Could not focus {app}")

        if action == "wait_for_element":
            element = str(params.get("element") or params.get("target") or "").strip()
            ok, message = _find_and_click(element, params.get("app"))
            return SkillResult(success=ok, output=message if ok else None, error=None if ok else message)

        if action == "get_active_window":
            title = _get_active_window_title()
            return SkillResult(success=True, output=f"Active window: {title}")

        return SkillResult(
            success=False,
            output=None,
            error="Unknown action. Use: click, type, type_active, press, hotkey, focus, wait_for_element, get_active_window",
        )
