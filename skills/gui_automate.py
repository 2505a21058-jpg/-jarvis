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

import logging
import platform
import re
import time

from config import (
    GUI_CLICK_TIMEOUT_SECONDS,
    GUI_FALLBACK_TYPE_WAIT_SECONDS,
    GUI_FOCUS_PAUSE_SECONDS,
    GUI_TYPE_TIMEOUT_SECONDS,
    GUI_WAIT_POLL_SECONDS,
)
from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.gui_automate")

_IS_WINDOWS = platform.system() == "Windows"
_CLICKABLE_CONTROL_TYPES = ("Button", "Hyperlink", "MenuItem", "TabItem", "ListItem", "CheckBox", "RadioButton")
_KEY_ALIASES = {
    "esc": "escape",
    "return": "enter",
    "windows": "win",
    "control": "ctrl",
    "cmd": "win",
    "command": "win",
}


def _get_pywinauto():
    """Lazy import pywinauto — graceful if not installed."""
    try:
        import pywinauto
        return pywinauto
    except ImportError:
        return None


def _title_regex(element_name: str) -> str:
    return rf".*{re.escape(str(element_name or '').strip())}.*"


def _element_label(element) -> str:
    for attr in ("window_text", "texts"):
        try:
            value = getattr(element, attr)()
            if isinstance(value, list):
                value = " ".join(str(item) for item in value)
            if str(value or "").strip():
                return str(value).strip()
        except Exception:
            continue
    return ""


def _click_candidate(element, element_name: str) -> tuple[bool, str]:
    try:
        element.click_input()
        return True, f"Clicked '{element_name}'"
    except Exception as exc:
        return False, str(exc)


def _find_descendant_by_name(window, element_name: str):
    target = str(element_name or "").strip().lower()
    if not target:
        return None

    try:
        descendants = window.descendants()
    except Exception as exc:
        logger.debug("Could not enumerate descendants for '%s': %s", element_name, exc)
        return None

    # Partial accessible-name matching lets Jarvis click labels that differ slightly from the spoken phrase.
    for element in descendants:
        label = _element_label(element).lower()
        if target and target in label:
            return element
    return None


def _find_in_window(window, element_name: str):
    candidates = [
        lambda: window.child_window(title=element_name, found_index=0),
        lambda: window.child_window(title_re=_title_regex(element_name), found_index=0),
    ]
    candidates.extend(
        lambda control_type=control_type: window.child_window(
            title_re=_title_regex(element_name),
            control_type=control_type,
            found_index=0,
        )
        for control_type in _CLICKABLE_CONTROL_TYPES
    )

    for build_candidate in candidates:
        try:
            return build_candidate()
        except Exception as exc:
            logger.debug("Candidate lookup failed for '%s': %s", element_name, exc)

    return _find_descendant_by_name(window, element_name)


def _click_in_window(window, element_name: str) -> tuple[bool, str]:
    element = _find_in_window(window, element_name)
    if element is not None:
        ok, message = _click_candidate(element, element_name)
        if ok:
            return True, message
        logger.debug("Element click failed for '%s': %s", element_name, message)
    return False, f"Element '{element_name}' not found in window"


def _normalize_keys(sequence: str) -> list[str]:
    raw_keys = re.split(r"\s*\+\s*|\s+", str(sequence or "").strip().lower())
    return [_KEY_ALIASES.get(key, key) for key in raw_keys if key]


def _press_key_sequence(sequence: str) -> tuple[bool, str]:
    try:
        import pyautogui

        keys = _normalize_keys(sequence)
        if not keys:
            return False, "No key sequence provided"
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return True, f"Pressed {'+'.join(keys)}"
    except Exception as exc:
        return False, f"Key press failed: {exc}"


def _connect_window(app_name: str = "", timeout: float = GUI_CLICK_TIMEOUT_SECONDS):
    if not _IS_WINDOWS:
        return None
    pw = _get_pywinauto()
    if not pw:
        return None

    try:
        from pywinauto import Application, Desktop

        if app_name:
            app = Application(backend="uia").connect(title_re=f".*{re.escape(app_name)}.*", timeout=timeout)
            return app.top_window()
        return Desktop(backend="uia").active()
    except Exception as exc:
        logger.debug("Could not connect to window '%s': %s", app_name, exc)
        return None


def _focus_window(app_name: str = "") -> tuple[bool, str]:
    window = _connect_window(app_name)
    if window is None:
        return False, f"Window '{app_name or 'active'}' not found"
    try:
        window.set_focus()
        time.sleep(GUI_FOCUS_PAUSE_SECONDS)
        return True, f"Focused {app_name or 'active window'}"
    except Exception as exc:
        logger.debug("pywinauto focus failed for '%s': %s", app_name, exc)
        try:
            from skills.utils.window_focus import focus_window_by_title

            title = _element_label(window) or app_name
            if title and focus_window_by_title(title):
                return True, f"Focused {title}"
        except Exception as fallback_exc:
            logger.debug("Fallback focus failed for '%s': %s", app_name, fallback_exc)
        return False, f"Could not focus {app_name or 'active window'}: {exc}"


def _wait_for_element(element_name: str, app_name: str = "", timeout: float = GUI_CLICK_TIMEOUT_SECONDS) -> tuple[bool, str]:
    deadline = time.monotonic() + max(timeout, 0.5)
    while time.monotonic() < deadline:
        window = _connect_window(app_name, timeout=min(timeout, GUI_CLICK_TIMEOUT_SECONDS))
        if window is not None and _find_in_window(window, element_name) is not None:
            return True, f"Found '{element_name}'"
        time.sleep(GUI_WAIT_POLL_SECONDS)
    return False, f"Element '{element_name}' did not appear within {timeout:.1f}s"


def _accessibility_snapshot(app_name: str = "", limit: int = 40) -> list[str]:
    window = _connect_window(app_name)
    if window is None:
        return []
    labels: list[str] = []
    try:
        window_label = _element_label(window)
        if window_label:
            labels.append(window_label)
        for element in window.descendants()[: max(int(limit or 0), 1)]:
            label = _element_label(element)
            if label and label not in labels:
                labels.append(label)
    except Exception as exc:
        logger.debug("Accessibility snapshot failed for '%s': %s", app_name, exc)
    return labels[:limit]


def _type_active(text: str) -> tuple[bool, str]:
    cleaned = str(text or "")
    if not cleaned:
        return False, "No text provided"
    try:
        import pyautogui

        pyautogui.write(cleaned, interval=0.02)
        return True, f"Typed {len(cleaned)} characters"
    except Exception as exc:
        return False, f"Active typing failed: {exc}"


def _find_and_click(element_name: str, app_name: str = None, timeout: float = GUI_CLICK_TIMEOUT_SECONDS) -> tuple[bool, str]:
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
        from pywinauto import Application, Desktop

        # Find element across all windows
        desktop = Desktop(backend="uia")

        # Search in specific app window if provided
        if app_name:
            try:
                app = Application(backend="uia").connect(title_re=f".*{app_name}.*", timeout=timeout)
                window = app.top_window()
                success, message = _click_in_window(window, element_name)
                if success:
                    return True, f"{message} in {app_name}"
            except Exception as e:
                logger.debug(f"App-specific search failed: {e}, trying desktop search")

        # Search across all windows
        windows = desktop.windows()
        for window in windows:
            try:
                success, message = _click_in_window(window, element_name)
                if success:
                    return True, message
            except Exception as exc:
                logger.debug("Window did not contain target element '%s': %s", element_name, exc)
                continue

        return False, f"Element '{element_name}' not found on screen"

    except Exception as e:
        logger.error(f"GUI click failed: {e}")
        return False, str(e)


def _type_into_app(app_name: str, text: str, timeout: float = GUI_TYPE_TIMEOUT_SECONDS) -> tuple[bool, str]:
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
        time.sleep(GUI_FOCUS_PAUSE_SECONDS)

        # Type text
        window.type_keys(text, with_spaces=True, pause=0.02)
        return True, f"Opened {app_name} and typed: {text[:60]}"

    except Exception as e:
        logger.error(f"Type into app failed: {e}")
        # Fallback to pyautogui
        try:
            import pyautogui
            time.sleep(GUI_FALLBACK_TYPE_WAIT_SECONDS)
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
    except Exception as exc:
        logger.debug("win32gui active window lookup failed: %s", exc)
        try:
            from pywinauto import Desktop
            return Desktop(backend="uia").active().window_text()
        except Exception as exc:
            # Active-window fallback failures are logged so empty titles can be diagnosed.
            logger.debug("pywinauto active window lookup failed: %s", exc)
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

        if action in {"press", "hotkey"}:
            sequence = str(params.get("keys") or params.get("key") or params.get("element") or "").strip()
            success, message = _press_key_sequence(sequence)
            return SkillResult(success=success, output=message if success else None, error=None if success else message)

        if action == "focus":
            app = params.get("app", "").strip()
            success, message = _focus_window(app)
            return SkillResult(success=success, output=message if success else None, error=None if success else message)

        if action == "wait_for_element":
            element = params.get("element", "").strip()
            app = params.get("app", "").strip()
            timeout = float(params.get("timeout") or GUI_CLICK_TIMEOUT_SECONDS)
            success, message = _wait_for_element(element, app, timeout)
            return SkillResult(success=success, output=message if success else None, error=None if success else message)

        if action == "type_active":
            text = str(params.get("text") or "").strip()
            success, message = _type_active(text)
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
            error=f"Unknown action '{action}'. Use: click, type, type_active, press, hotkey, focus, wait_for_element, get_active_window"
        )
