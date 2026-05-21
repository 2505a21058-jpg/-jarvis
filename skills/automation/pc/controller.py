"""
skills/automation/pc/controller.py

High-level PC automation controller.
Single entry point for all PC actions.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("jarvis.pc.controller")


class PCController:
    def open_app(self, app_name: str) -> str:
        from skills.automation.pc.app_launcher import is_browser_app, launch_app

        if is_browser_app(app_name):
            return f"'{app_name}' is web-based - routing to browser skill"
        return launch_app(app_name)

    def type_text(self, text: str) -> str:
        from skills.automation.pc.input_handler import type_text

        ok = type_text(text)
        return f"Typed: {text[:60]}" if ok else "Could not type text"

    def press(self, key: str) -> str:
        from skills.automation.pc.input_handler import press_key

        ok = press_key(key)
        return f"Pressed {key}" if ok else f"Could not press {key}"

    def hotkey(self, *keys: str) -> str:
        from skills.automation.pc.input_handler import hotkey

        ok = hotkey(*keys)
        combo = "+".join(keys)
        return f"Pressed {combo}" if ok else f"Could not press {combo}"

    def open_and_type(self, app_name: str, text: str, wait_s: float = 2.0) -> str:
        from skills.automation.pc.app_launcher import bring_to_front, wait_for_window

        result = self.open_app(app_name)
        if "Could not" in result:
            return result

        wait_for_window(app_name, timeout=max(1, int(wait_s)))
        bring_to_front(app_name)
        type_result = self.type_text(text)
        return f"{result}. {type_result}"

    def copy(self):
        return self.hotkey("ctrl", "c")

    def paste(self):
        return self.hotkey("ctrl", "v")

    def select_all(self):
        return self.hotkey("ctrl", "a")

    def close_window(self):
        return self.hotkey("alt", "F4")

    def new_window(self):
        return self.hotkey("ctrl", "n")


_pc: Optional[PCController] = None


def get_pc() -> PCController:
    global _pc
    if _pc is None:
        _pc = PCController()
    return _pc
