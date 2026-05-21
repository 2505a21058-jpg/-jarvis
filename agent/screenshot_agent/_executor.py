"""
agent/screenshot_agent/_executor.py

Executes a PlannedAction on the real desktop using coordinate-based
input. Tries pyautogui first, falls back to SendInput (win32) when
pyautogui fails (e.g. in games, locked apps, or DPI-aware contexts).

Takes before/after screenshots for the verifier.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from agent.screenshot_agent._perception import _take_screenshot

logger = logging.getLogger("jarvis.screenshot_agent.executor")


@dataclass
class ActionResult:
    action: str
    success: bool
    message: str = ""
    before_b64: str = ""
    after_b64: str = ""


def _screenshot_b64() -> str:
    raw, _, _ = _take_screenshot() or (b"", 0, 0)
    if raw:
        import base64
        return base64.b64encode(raw).decode("utf-8")
    return ""


def _try_pyautogui_click(x: int, y: int) -> bool:
    try:
        import pyautogui
        pyautogui.click(x, y)
        return True
    except Exception as exc:
        logger.debug("pyautogui click failed: %s", exc)
        return False


def _try_sendinput_click(x: int, y: int) -> bool:
    try:
        from agent.hands.engines.sendinput_engine import _send_mouse_click
        return _send_mouse_click(x, y)
    except Exception as exc:
        logger.debug("SendInput click failed: %s", exc)
        return False


def _click(x: int, y: int) -> bool:
    if _try_pyautogui_click(x, y):
        return True
    return _try_sendinput_click(x, y)


def _try_pyautogui_type(text: str) -> bool:
    try:
        import pyautogui
        pyautogui.write(text, interval=0.02)
        return True
    except Exception as exc:
        logger.debug("pyautogui type failed: %s", exc)
        return False


def _try_sendinput_type(text: str) -> bool:
    try:
        from agent.hands.engines.sendinput_engine import SendInputEngine
        engine = SendInputEngine()
        return engine.type_text(text)
    except Exception as exc:
        logger.debug("SendInput type failed: %s", exc)
        return False


def _type(text: str) -> bool:
    if _try_pyautogui_type(text):
        return True
    return _try_sendinput_type(text)


def _try_pyautogui_key(keys: str) -> bool:
    try:
        import pyautogui
        parts = keys.lower().split("+")
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        return True
    except Exception as exc:
        logger.debug("pyautogui key failed: %s", exc)
        return False


def _try_sendinput_key(combo: str) -> bool:
    try:
        from agent.hands.engines.sendinput_engine import SendInputEngine
        engine = SendInputEngine()
        parts = combo.lower().split("+")
        return engine.hotkey(*parts)
    except Exception as exc:
        logger.debug("SendInput key failed: %s", exc)
        return False


def _key(keys: str) -> bool:
    if _try_pyautogui_key(keys):
        return True
    return _try_sendinput_key(keys)


def _scroll(direction: str, amount: int = 1) -> bool:
    try:
        import pyautogui
        clicks = amount if direction == "down" else -amount
        pyautogui.scroll(clicks)
        return True
    except Exception as exc:
        logger.debug("pyautogui scroll failed: %s", exc)
        try:
            from agent.hands.engines.sendinput_engine import SendInputEngine
            engine = SendInputEngine()
            key = "pagedown" if direction == "down" else "pageup"
            return engine.hotkey(key)
        except Exception as exc2:
            logger.debug("SendInput scroll failed: %s", exc2)
            return False


def execute(
    action: str,
    *,
    x: Optional[int] = None,
    y: Optional[int] = None,
    text: Optional[str] = None,
    keys: Optional[str] = None,
    direction: Optional[str] = None,
    amount: int = 1,
    seconds: float = 1.0,
) -> ActionResult:
    before = _screenshot_b64()

    if action == "click":
        if x is None or y is None:
            return ActionResult("click", False, "Missing click coordinates", before, "")
        ok = _click(x, y)
        msg = f"Clicked ({x}, {y})" if ok else f"Click at ({x}, {y}) failed"
        return ActionResult("click", ok, msg, before, _screenshot_b64() if ok else "")

    if action == "type":
        if not text:
            return ActionResult("type", False, "No text to type", before, "")
        ok = _type(text)
        msg = f"Typed {len(text)} characters" if ok else "Type failed"
        return ActionResult("type", ok, msg, before, _screenshot_b64() if ok else "")

    if action == "key":
        if not keys:
            return ActionResult("key", False, "No key combo", before, "")
        ok = _key(keys)
        msg = f"Sent {keys}" if ok else f"Key combo {keys} failed"
        return ActionResult("key", ok, msg, before, _screenshot_b64() if ok else "")

    if action == "scroll":
        dir = direction or "down"
        ok = _scroll(dir, amount)
        msg = f"Scrolled {dir}" if ok else f"Scroll {dir} failed"
        return ActionResult("scroll", ok, msg, before, _screenshot_b64() if ok else "")

    if action == "wait":
        time.sleep(seconds)
        return ActionResult("wait", True, f"Waited {seconds}s", before, _screenshot_b64())

    if action == "zoom":
        return ActionResult("zoom", True, "Zoom will be handled by next perception cycle", before, "")

    if action in ("done", "fail"):
        return ActionResult(action, True, "", before, "")

    return ActionResult(action, False, f"Unknown action: {action}", before, "")
