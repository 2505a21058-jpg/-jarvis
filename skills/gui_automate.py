"""
skills/gui_automate.py

Reliable Windows GUI automation using accessibility tree.
Inspired by Windows-Use (github.com/CursorTouch/Windows-Use).

Uses pywinauto (Windows Accessibility API) instead of coordinate-based
pyautogui. Finds elements by name/type rather than screen position.
Much more reliable than zone-based clicking.

Dependencies: pip install pywinauto
Platform: Windows only (graceful degradation on other platforms)
"""

import platform
import time
import logging
from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.gui_automate")

_IS_WINDOWS = platform.system() == "Windows"


def _get_pywinauto():
    """Lazy import pywinauto — graceful if not installed."""
    try:
        import pywinauto
        return pywinauto
    except ImportError:
        return None


def _find_and_click(element_name: str, app_name: str = None, timeout: float = 5.0) -> tuple[bool, str]:
    """
    Find a UI element by name using accessibility tree and click it.
    Much more reliable than coordinate-based clicking.

    Returns (success, message).
    """
    if not _IS_WINDOWS:
        return False, "GUI automation only supported on Windows"

    pw = _get_pywinauto()
    if not pw:
        return False, "pywinauto not installed. Run: pip install pywinauto"

    try:
        from pywinauto import Desktop, Application
        from pywinauto.findwindows import ElementNotFoundError

        # Find element across all windows
        desktop = Desktop(backend="uia")

        # Search in specific app window if provided
        if app_name:
            try:
                app = Application(backend="uia").connect(title_re=f".*{app_name}.*", timeout=timeout)
                window = app.top_window()
                element = window.child_window(title=element_name, found_index=0)
                element.click_input()
                return True, f"Clicked '{element_name}' in {app_name}"
            except Exception as e:
                logger.debug(f"App-specific search failed: {e}, trying desktop search")

        # Search across all windows
        windows = desktop.windows()
        for window in windows:
            try:
                element = window.child_window(title=element_name, found_index=0)
                element.click_input()
                return True, f"Clicked '{element_name}'"
            except Exception:
                continue

        return False, f"Element '{element_name}' not found on screen"

    except Exception as e:
        logger.error(f"GUI click failed: {e}")
        return False, str(e)


def _type_into_app(app_name: str, text: str, timeout: float = 8.0) -> tuple[bool, str]:
    """
    Open an app and type text into it using accessibility API.
    Waits for app to actually be ready, not just a fixed sleep.
    """
    if not _IS_WINDOWS:
        return False, "GUI automation only supported on Windows"

    pw = _get_pywinauto()
    if not pw:
        return False, "pywinauto not installed. Run: pip install pywinauto"

    import subprocess
    from skills.open_app import APP_MAP_WINDOWS, WEB_APPS

    # Open the app
    cmd_options = APP_MAP_WINDOWS.get(app_name.lower(), [app_name])
    process = None

    for cmd in cmd_options:
        try:
            process = subprocess.Popen([cmd] if isinstance(cmd, str) else cmd)
            break
        except (FileNotFoundError, OSError):
            continue

    if not process:
        return False, f"Could not launch '{app_name}'"

    # Wait for app window to appear (proper wait, not sleep)
    try:
        from pywinauto import Application
        app = Application(backend="uia").connect(
            process=process.pid,
            timeout=timeout
        )
        window = app.top_window()
        window.wait("ready", timeout=timeout)
        window.set_focus()
        time.sleep(0.3)  # brief pause after focus

        # Type text
        window.type_keys(text, with_spaces=True, pause=0.02)
        return True, f"Opened {app_name} and typed: {text[:60]}"

    except Exception as e:
        logger.error(f"Type into app failed: {e}")
        # Fallback to pyautogui
        try:
            import pyautogui
            time.sleep(1.5)  # minimal fallback sleep
            pyautogui.typewrite(text, interval=0.03)
            return True, f"Opened {app_name} and typed (fallback): {text[:60]}"
        except Exception as e2:
            return False, f"Both methods failed: {e2}"


def _get_active_window_title() -> str:
    """Get the title of the currently active window."""
    if not _IS_WINDOWS:
        return ""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd)
    except Exception:
        try:
            from pywinauto import Desktop
            return Desktop(backend="uia").active().window_text()
        except Exception:
            return ""


class GUIAutomateSkill(SkillBase):
    name = "gui_automate"
    description = "Reliable Windows GUI automation — open apps, click elements, type text"
    timeout_seconds = 20.0

    def execute(self, params: dict, state) -> SkillResult:
        action = params.get("action", "").lower()

        if action == "click":
            element = params.get("element", "").strip()
            app = params.get("app", "").strip()
            if not element:
                return SkillResult(success=False, output=None, error="No element name to click")
            success, message = _find_and_click(element, app or None)
            return SkillResult(success=success, output=message if success else None, error=None if success else message)

        if action == "type":
            app = params.get("app", "").strip()
            text = params.get("text", "").strip()
            if not app or not text:
                return SkillResult(success=False, output=None, error="Need both 'app' and 'text' params")
            success, message = _type_into_app(app, text)
            return SkillResult(success=success, output=message if success else None, error=None if success else message)

        if action == "get_active_window":
            title = _get_active_window_title()
            return SkillResult(success=True, output=f"Active window: {title}")

        return SkillResult(
            success=False, output=None,
            error=f"Unknown action '{action}'. Use: click, type, get_active_window"
        )
