from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from skills.base import SkillBase, SkillResult
from .utils.focus import focus_app


MAX_TYPE_TEXT_LENGTH = 1000
TYPE_INTERVAL_SECONDS = 0.01
TYPE_TIMEOUT_SECONDS = 5.0


def _tool_result(success: bool, output=None, error: str | None = None):
    return {
        "success": bool(success),
        "output": output,
        "error": error,
    }


def _clean_text(text: str) -> str:
    return str(text or "").strip()


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


def _perform_type(active_app: str, cleaned_text: str) -> None:
    import pyautogui

    if not focus_app(active_app):
        raise RuntimeError(f"Could not focus {active_app} for typing.")

    pyautogui.write(cleaned_text, interval=TYPE_INTERVAL_SECONDS)


class TypeTextSkill(SkillBase):
    name = "type_text"
    description = "Types text into the active application"
    timeout_seconds = TYPE_TIMEOUT_SECONDS

    def execute(self, params: dict, state: Any) -> SkillResult:
        cleaned_text = _clean_text(params.get("text") or params.get("target") or "")
        if not cleaned_text:
            message = "Nothing to type."
            return SkillResult(success=False, output=message, error=message)

        if len(cleaned_text) > MAX_TYPE_TEXT_LENGTH:
            message = f"Text is too long to type safely. Limit is {MAX_TYPE_TEXT_LENGTH} characters."
            return SkillResult(success=False, output=message, error=message)

        active_platform = _state_get(state, "active_platform", "default")
        active_app = _state_get(state, "active_app", active_platform)
        if not active_app or active_app == "default":
            message = "No active app is set for typing."
            return SkillResult(success=False, output=message, error=message)

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_perform_type, active_app, cleaned_text)
                future.result(timeout=min(self.timeout_seconds, TYPE_TIMEOUT_SECONDS))
        except FuturesTimeoutError:
            return SkillResult(success=False, output=None, error="Timeout")
        except Exception as exc:
            error = f"Failed to type text: {exc}"
            return SkillResult(success=False, output=error, error=error)

        _state_set(state, "last_action", f"type:{active_app}")
        message = f"Typed text into {active_app}."
        return SkillResult(success=True, output=message)


def type_text(text: str, state: Any = None) -> dict[str, Any]:
    result = TypeTextSkill().run({"text": text}, state or {})
    return _tool_result(result.success, result.output, result.error)
