"""
agent/hands/engines/winapi_engine.py

Windows API engine - direct Win32 message control.
WM_SETTEXT/BM_CLICK - instant, no coordinates.
Works on: legacy Win32 apps, Notepad, classic dialogs
"""

from __future__ import annotations

import logging
from typing import Optional

from agent.hands.engines.base import ActionResult, fail, ok
from rawvision.output.schema import UIElement

logger = logging.getLogger("jarvis.hands.winapi")

WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
EM_SETSEL = 0x00B1
WM_CHAR = 0x0102


class WinAPIEngine:
    """Direct Win32 message-based control."""

    name = "winapi"

    def set_text(self, hwnd: int, text: str) -> bool:
        """Set text in edit control directly via WM_SETTEXT."""
        result = _send_message(hwnd, WM_SETTEXT, 0, text)
        logger.debug("[WINAPI] WM_SETTEXT hwnd=%s text=%r", hwnd, text[:50])
        return result is not None

    def click_button(self, hwnd: int) -> bool:
        """Click button via BM_CLICK."""
        result = _send_message(hwnd, BM_CLICK, 0, 0)
        logger.debug("[WINAPI] BM_CLICK hwnd=%s", hwnd)
        return result is not None

    def get_text(self, hwnd: int) -> str:
        """Read text from window/control."""
        try:
            import ctypes

            length = ctypes.windll.user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, None)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, buf)
            return buf.value
        except Exception:
            return ""

    def bring_to_front(self, hwnd: int) -> bool:
        """Bring window to foreground."""
        try:
            import ctypes

            ctypes.windll.user32.ShowWindow(hwnd, 9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.warning("[WINAPI] bring_to_front failed: %s", e)
            return False

    def find_child_by_class(self, parent_hwnd: int, class_name: str) -> Optional[int]:
        """Find child control by window class name."""
        try:
            import ctypes

            hwnd = ctypes.windll.user32.FindWindowExW(parent_hwnd, None, class_name, None)
            return hwnd if hwnd else None
        except Exception:
            return None

    def click(self, element: UIElement) -> ActionResult:
        """Compatibility wrapper for router-style callers."""
        if not element.hwnd:
            return fail(self.name, "element has no hwnd")
        return ok(self.name, "BM_CLICK sent") if self.click_button(element.hwnd) else fail(self.name, "BM_CLICK failed")

    def type_text(self, element: UIElement, text: str) -> ActionResult:
        """Compatibility wrapper for router-style callers."""
        if not element.hwnd:
            return fail(self.name, "element has no hwnd")
        return ok(self.name, "WM_SETTEXT sent") if self.set_text(element.hwnd, text) else fail(self.name, "WM_SETTEXT failed")


def _send_message(hwnd: int, msg: int, wparam=0, lparam=0):
    try:
        import ctypes

        return ctypes.windll.user32.SendMessageW(int(hwnd), int(msg), wparam, lparam)
    except Exception as e:
        logger.warning("[WINAPI] SendMessage failed: %s", e)
        return None


WinApiEngine = WinAPIEngine
