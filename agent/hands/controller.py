"""
agent/hands/controller.py

HandsController - single entry point for all automation actions.
Routes to correct engine based on app type.
Never raises - all failures logged and return False/empty.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from agent.hands.engines.base import ActionResult, fail

logger = logging.getLogger("jarvis.hands")


class AwaitableBool:
    """Awaitable boolean used by the public async-style Hands API."""

    def __init__(self, coro):
        self._coro = coro

    def __await__(self):
        return self._coro.__await__()


class HandsController:
    """
    Zero-simulation app control.

    Routes actions based on app type:
      Chrome/Electron -> CDP engine
      Native Win32    -> UIA engine + WinAPI engine
      Terminal        -> Terminal engine
      Unknown/Game    -> SendInput engine (last resort)
    """

    def __init__(self, router=None):
        self.router = router
        self._cdp = None
        self._uia = None
        self._winapi = None
        self._terminal = None
        self._sendinput = None

    def _cdp_engine(self):
        if not self._cdp:
            from agent.hands.engines.cdp_engine import CDPEngine

            self._cdp = CDPEngine()
        return self._cdp

    def _uia_engine(self):
        if not self._uia:
            from agent.hands.engines.uia_engine import UIAEngine

            self._uia = UIAEngine()
        return self._uia

    def _winapi_engine(self):
        if not self._winapi:
            from agent.hands.engines.winapi_engine import WinAPIEngine

            self._winapi = WinAPIEngine()
        return self._winapi

    def _terminal_engine(self):
        if not self._terminal:
            from agent.hands.engines.terminal_engine import TerminalEngine

            self._terminal = TerminalEngine()
        return self._terminal

    def _sendinput_engine(self):
        if not self._sendinput:
            from agent.hands.engines.sendinput_engine import SendInputEngine

            self._sendinput = SendInputEngine()
        return self._sendinput

    def click(self, element, process_info=None):
        """Click element using best available method."""
        if self.router is not None:
            return self._router_action("click", element, process_info)
        return AwaitableBool(self._click_async(element))

    def type_text(self, *args, element=None, process_info=None):
        """Type text into element or focused control."""
        if self.router is not None:
            if len(args) == 2:
                target, text = args
            elif len(args) == 1:
                target, text = element, args[0]
            else:
                return fail("hands", "type_text requires text")
            return self._router_type(target, str(text), process_info)

        if len(args) == 2:
            if isinstance(args[0], str):
                text, target = args
            else:
                target, text = args
        elif len(args) == 1:
            text, target = args[0], element
        else:
            return AwaitableBool(_false())
        return AwaitableBool(self._type_text_async(str(text), target))

    def navigate(self, url: str):
        """Navigate browser to URL."""
        return self._cdp_engine().navigate(url)

    def evaluate(self, js: str):
        """Execute JavaScript in a browser/electron page."""
        return self._cdp_engine().evaluate(js)

    def fetch(self, url: str, method="GET", body=None):
        """HTTP request as the page using page auth/cookies."""
        return self._cdp_engine().fetch(url, method, body)

    def key(self, combo: str, element=None):
        """Press keyboard shortcut."""
        return AwaitableBool(self._key_async(combo, element=element))

    def run_command(self, command: str, timeout=30):
        """Execute terminal command."""
        return self._terminal_engine().run(command, timeout)

    def run_powershell(self, script: str, timeout=30):
        """Execute PowerShell script."""
        return self._terminal_engine().run_powershell(script, timeout)

    async def _click_async(self, element) -> bool:
        try:
            if getattr(element, "cdp_node_id", None):
                return bool(await self._cdp_engine().click(element.cdp_node_id))

            if getattr(element, "runtime_id", None):
                result = self._uia_engine().invoke(element.runtime_id)
                if result:
                    return True

            if getattr(element, "hwnd", None):
                return self._winapi_engine().click_button(element.hwnd)

            if getattr(element, "bbox", None):
                return self._sendinput_engine().click_element(element.bbox)

            element_name = None
            if hasattr(element, "name") and element.name:
                element_name = element.name
            elif hasattr(element, "texts"):
                try:
                    texts = element.texts()
                    if texts:
                        element_name = " ".join(str(t) for t in texts if t)
                except Exception:
                    pass

            if element_name:
                logger.info("[HANDS] No structural ID — trying screenshot-guided click for '%s'", element_name)
                try:
                    from agent.screenshot_agent import ScreenshotAgent
                    agent = ScreenshotAgent(max_steps=3, zoom_enabled=False)
                    result = agent.single_action("click", {"element": element_name})
                    if result.success:
                        return True
                except Exception as exc:
                    logger.debug("[HANDS] Screenshot click failed: %s", exc)

            logger.warning("[HANDS] Cannot click element: no ID or bbox")
            return False
        except Exception as exc:
            logger.warning("[HANDS] click failed: %s", exc)
            return False

    async def _type_text_async(self, text: str, element=None) -> bool:
        try:
            if element and getattr(element, "cdp_node_id", None):
                return bool(await self._cdp_engine().type_text(text, node_id=element.cdp_node_id))

            if element and getattr(element, "runtime_id", None) and getattr(element, "is_typeable", False):
                result = self._uia_engine().set_value(element.runtime_id, text)
                if result:
                    return True

            if element and getattr(element, "hwnd", None):
                return self._winapi_engine().set_text(element.hwnd, text)

            return bool(self._sendinput_engine().type_text(text))
        except Exception as exc:
            logger.warning("[HANDS] type_text failed: %s", exc)
            return False

    async def _key_async(self, combo: str, element=None) -> bool:
        try:
            if element and getattr(element, "cdp_node_id", None):
                return bool(await self._cdp_engine().key(combo))
            return self._sendinput_engine().hotkey(*combo.split("+"))
        except Exception as exc:
            logger.warning("[HANDS] key failed: %s", exc)
            return False

    def _router_action(self, action: str, element, process_info=None) -> ActionResult:
        try:
            engine = self.router.engine_for(action, element, process_info)
            if not hasattr(engine, action):
                return fail("hands", f"engine cannot {action}")
            return getattr(engine, action)(element)
        except Exception as exc:
            return fail("hands", str(exc))

    def _router_type(self, element, text: str, process_info=None) -> ActionResult:
        try:
            engine = self.router.engine_for("type_text", element, process_info)
            if not hasattr(engine, "type_text"):
                return fail("hands", "engine cannot type")
            return engine.type_text(element, text)
        except Exception as exc:
            return fail("hands", str(exc))


async def _false() -> bool:
    return False


_hands_instance: Optional[HandsController] = None


def get_hands() -> HandsController:
    global _hands_instance
    if _hands_instance is None:
        _hands_instance = HandsController()
    return _hands_instance
