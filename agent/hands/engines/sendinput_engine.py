"""
agent/hands/engines/sendinput_engine.py

SendInput engine - LAST RESORT ONLY.
Used for games and apps with no semantic API.
DPI-corrected, unicode-native.
"""

from __future__ import annotations

import ctypes
import logging
import time
from ctypes import wintypes

from agent.hands.engines.base import ActionResult, fail, ok
from rawvision.output.schema import BoundingBox, Point, UIElement
from rawvision.utils.spatial import dpi_correct, screen_to_logical

logger = logging.getLogger("jarvis.hands.sendinput")

_TYPE_DELAY = 0.03


class SendInputEngine:
    """
    Coordinate-based input simulation.
    Only use when no semantic API is available.
    """

    name = "sendinput"

    def click(self, point_or_element: Point | UIElement, double: bool = False):
        """Click at coordinates with DPI correction, or compatibility-click an element."""
        if isinstance(point_or_element, UIElement):
            if not point_or_element.center:
                return fail(self.name, "element has no click target")
            point = dpi_correct(point_or_element.center)
            success = _send_mouse_click(point.x, point.y, double=double) if double else _send_mouse_click(point.x, point.y)
            return ok(self.name, "clicked", x=point.x, y=point.y) if success else fail(self.name, "click failed", x=point.x, y=point.y)

        corrected = dpi_correct(point_or_element)
        success = _send_mouse_click(corrected.x, corrected.y, double=double) if double else _send_mouse_click(corrected.x, corrected.y)
        logger.debug("[SENDINPUT] Click at %s (corrected from %s)", corrected, point_or_element)
        return success

    def click_element(self, bbox: BoundingBox) -> bool:
        """Click center of element bounding box."""
        logical = screen_to_logical(bbox)
        return bool(self.click(logical.center))

    def type_text(self, text_or_element, text: str | None = None, method: str = "auto"):
        """
        Type text. Auto tries win32 first, then pyautogui.
        Compatibility form: type_text(element, text) returns ActionResult.
        """
        compatibility = text is not None
        payload = str(text if compatibility else text_or_element or "")

        success = False
        if method in ("auto", "win32"):
            success = self._type_win32(payload)
        if not success and method in ("auto", "pyautogui"):
            success = self._type_pyautogui(payload)
        if not success:
            success = self._type_keyboard_lib(payload)

        if compatibility:
            return ok(self.name, "typed") if success else fail(self.name, "text input failed")
        return success

    def press_key(self, key: str) -> bool:
        try:
            import pyautogui

            pyautogui.press(key)
            return True
        except Exception:
            try:
                import keyboard

                keyboard.press_and_release(key)
                return True
            except Exception as e:
                logger.error("[SENDINPUT] press_key failed: %s", e)
                return False

    def hotkey(self, *keys: str) -> bool:
        try:
            import pyautogui

            pyautogui.hotkey(*keys)
            return True
        except Exception:
            try:
                import keyboard

                keyboard.press_and_release("+".join(keys))
                return True
            except Exception as e:
                logger.error("[SENDINPUT] hotkey failed: %s", e)
                return False

    def _type_win32(self, text: str) -> bool:
        for char in text:
            if not _send_unicode_char(char):
                return False
            time.sleep(_TYPE_DELAY)
        return True

    def _type_pyautogui(self, text: str) -> bool:
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.write(text, interval=_TYPE_DELAY)
            return True
        except Exception as e:
            logger.debug("[SENDINPUT] pyautogui type failed: %s", e)
            return False

    def _type_keyboard_lib(self, text: str) -> bool:
        try:
            import keyboard

            keyboard.write(text, delay=_TYPE_DELAY)
            return True
        except Exception as e:
            logger.debug("[SENDINPUT] keyboard lib failed: %s", e)
            return False


def _send_mouse_click(x: int, y: int, double: bool = False) -> bool:
    try:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        clicks = 2 if double else 1
        inputs = []
        for _ in range(clicks):
            inputs.extend((_mouse_input(0x0002), _mouse_input(0x0004)))
        array_type = INPUT * len(inputs)
        sent = ctypes.windll.user32.SendInput(len(inputs), ctypes.byref(array_type(*inputs)), ctypes.sizeof(INPUT))
        return sent == len(inputs)
    except Exception:
        return False


def _send_unicode_char(char: str) -> bool:
    try:
        code = ord(char)
        down = _keyboard_input(code, flags=0x0004)
        up = _keyboard_input(code, flags=0x0004 | 0x0002)
        sent = ctypes.windll.user32.SendInput(2, ctypes.byref((INPUT * 2)(down, up)), ctypes.sizeof(INPUT))
        return sent == 2
    except Exception:
        return False


def _mouse_input(flags: int):
    return INPUT(
        type=0,
        union=INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, None)),
    )


def _keyboard_input(scan: int, flags: int):
    return INPUT(
        type=1,
        union=INPUTUNION(ki=KEYBDINPUT(0, scan, flags, 0, None)),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", INPUTUNION),
    ]
