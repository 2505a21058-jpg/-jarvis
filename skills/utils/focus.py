import logging
import time


logger = logging.getLogger("jarvis.skills.focus")


def focus_app(app_name: str = "") -> bool:
    try:
        import pyautogui

        pyautogui.hotkey("alt", "tab")
        time.sleep(0.2)
        return True
    except Exception as exc:
        # Focus failures are logged so callers can diagnose optional GUI dependency issues.
        logger.debug("Could not focus app '%s': %s", app_name, exc)
        return False
