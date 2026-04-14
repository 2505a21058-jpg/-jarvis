import time

from memory.context import SESSION_CONTEXT
from .utils.focus import focus_app


MAX_TYPE_TEXT_LENGTH = 1000
TYPE_INTERVAL_SECONDS = 0.01
FOCUS_READY_DELAY_SECONDS = 0.2


def _tool_result(success: bool, output=None, error: str | None = None):
    return {
        "success": bool(success),
        "output": output,
        "error": error,
    }


def _clean_text(text: str) -> str:
    return str(text or "").strip()


def type_text(text: str) -> str:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        message = "Nothing to type."
        return _tool_result(False, message, message)

    if len(cleaned_text) > MAX_TYPE_TEXT_LENGTH:
        message = f"Text is too long to type safely. Limit is {MAX_TYPE_TEXT_LENGTH} characters."
        return _tool_result(False, message, message)

    active_app = SESSION_CONTEXT.get_app()
    if not active_app:
        message = "No active app is set for typing."
        return _tool_result(False, message, message)

    try:
        import pyautogui

        if not focus_app(active_app):
            message = f"Could not focus {active_app} for typing."
            return _tool_result(False, message, message)

        time.sleep(FOCUS_READY_DELAY_SECONDS)
        pyautogui.write(cleaned_text, interval=TYPE_INTERVAL_SECONDS)
        SESSION_CONTEXT.last_action = f"type:{active_app or 'active_app'}"

        message = f"Typed text into {active_app}."
        return _tool_result(True, message, None)
    except Exception as e:
        error = f"Failed to type text: {str(e)}"
        return _tool_result(False, error, error)
