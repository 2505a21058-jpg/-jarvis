import time

from memory.context import SESSION_CONTEXT
from .utils.focus import focus_app


MAX_TYPE_TEXT_LENGTH = 1000
TYPE_INTERVAL_SECONDS = 0.01
FOCUS_READY_DELAY_SECONDS = 0.2


def _clean_text(text: str) -> str:
    return str(text or "").strip()


def type_text(text: str) -> str:
    cleaned_text = _clean_text(text)
    if not cleaned_text:
        return "Nothing to type."

    if len(cleaned_text) > MAX_TYPE_TEXT_LENGTH:
        return f"Text is too long to type safely. Limit is {MAX_TYPE_TEXT_LENGTH} characters."

    active_app = SESSION_CONTEXT.get_app()
    if not active_app:
        return "No active app is set for typing."

    try:
        import pyautogui

        if not focus_app(active_app):
            return f"Could not focus {active_app} for typing."

        time.sleep(FOCUS_READY_DELAY_SECONDS)
        pyautogui.write(cleaned_text, interval=TYPE_INTERVAL_SECONDS)
        SESSION_CONTEXT.last_action = f"type:{active_app or 'active_app'}"

        return f"Typed text into {active_app}."
    except Exception as e:
        return f"Failed to type text: {str(e)}"
