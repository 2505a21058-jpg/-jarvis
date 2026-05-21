"""
skills/automation/pc/input_handler.py

Multi-strategy keyboard and mouse input.
win32api → pyautogui → keyboard library
"""

import logging
import time

logger = logging.getLogger("jarvis.pc.input")

_DELAY = 0.03


def type_text(text: str, method: str = "auto") -> bool:
    """
    Type text using best available method.
    auto: tries win32 first, then pyautogui, then keyboard lib.
    """
    if method == "win32"    : return _type_win32(text)
    if method == "pyautogui": return _type_pyautogui(text)
    if method == "keyboard" : return _type_kb(text)
    # auto
    return _type_win32(text) or _type_pyautogui(text) or _type_kb(text)


def _type_win32(text: str) -> bool:
    try:
        import win32api, win32con
        for ch in text:
            vk = win32api.VkKeyScan(ch) & 0xFF
            if vk:
                win32api.keybd_event(vk, 0, 0, 0)
                time.sleep(0.01)
                win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(_DELAY)
        return True
    except Exception as e:
        logger.debug(f"[INPUT] win32 failed: {e}")
        return False


def _type_pyautogui(text: str) -> bool:
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.write(text, interval=_DELAY)
        return True
    except Exception as e:
        logger.debug(f"[INPUT] pyautogui failed: {e}")
        return False


def _type_kb(text: str) -> bool:
    try:
        import keyboard
        keyboard.write(text, delay=_DELAY)
        return True
    except Exception as e:
        logger.debug(f"[INPUT] keyboard lib failed: {e}")
        return False


def press_key(key: str) -> bool:
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
            logger.error(f"[INPUT] press_key failed: {e}")
            return False


def hotkey(*keys: str) -> bool:
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
            logger.error(f"[INPUT] hotkey failed: {e}")
            return False


def click_at(x: int, y: int, double: bool = False) -> bool:
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        if double:
            pyautogui.doubleClick(x, y)
        else:
            pyautogui.click(x, y)
        return True
    except Exception as e:
        logger.error(f"[INPUT] click_at failed: {e}")
        return False
