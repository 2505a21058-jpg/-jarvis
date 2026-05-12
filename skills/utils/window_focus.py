import logging
import time


logger = logging.getLogger("jarvis.skills.window_focus")


def _normalize_title(text: str) -> str:
    return str(text or "").strip().lower()


def find_window_by_title(title: str):
    needle = _normalize_title(title)
    if not needle:
        return None

    try:
        import pygetwindow as gw

        for window in gw.getAllWindows():
            window_title = _normalize_title(getattr(window, "title", ""))
            if needle in window_title:
                return window
    except Exception as exc:
        # Window enumeration failures are logged so missing pygetwindow/platform issues are visible.
        logger.debug("Window lookup failed for title '%s': %s", title, exc)
        return None

    return None


def focus_window_by_title(title: str) -> bool:
    window = find_window_by_title(title)
    if window is None:
        return False

    try:
        if getattr(window, "isMinimized", False):
            window.restore()
            time.sleep(0.1)
        window.activate()
        time.sleep(0.15)
        return True
    except Exception as exc:
        # Window activation failures are logged while preserving the boolean API.
        logger.debug("Could not focus window '%s': %s", title, exc)
        return False


def focus_any_window(titles: list[str]) -> bool:
    for title in titles:
        if focus_window_by_title(title):
            return True
    return False
