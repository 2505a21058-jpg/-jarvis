"""
agent/hands/engines/uia_engine.py

UIA engine - controls native Windows apps.
Direct UIA invoke/setvalue - no coordinates.
Works on: Notepad, Explorer, Win32 apps, WPF, WinForms, Office
"""

from __future__ import annotations

import logging
from typing import Optional

from agent.hands.engines.base import ActionResult, fail, ok
from rawvision.output.schema import UIElement

logger = logging.getLogger("jarvis.hands.uia")

_UIA_INVOKE_PATTERN = 10000
_UIA_VALUE_PATTERN = 10002


class UIAEngine:
    """Windows UIA control - invoke elements directly."""

    name = "uia"

    def invoke(self, runtime_id: str) -> bool:
        """Invoke element by UIA runtime ID."""
        try:
            uia = self._get_uia()
            if not uia:
                return False

            el = self._find_by_runtime_id(uia, runtime_id)
            if not el:
                return False

            pattern = el.GetCurrentPattern(_UIA_INVOKE_PATTERN)
            if pattern:
                pattern.Invoke()
                logger.debug("[UIA] Invoked: %s", runtime_id)
                return True
        except Exception as e:
            logger.warning("[UIA] invoke failed %s: %s", runtime_id, e)
        return False

    def set_value(self, runtime_id: str, value: str) -> bool:
        """Set input field value directly."""
        try:
            uia = self._get_uia()
            if not uia:
                return False

            el = self._find_by_runtime_id(uia, runtime_id)
            if not el:
                return False

            pattern = el.GetCurrentPattern(_UIA_VALUE_PATTERN)
            if pattern:
                pattern.SetValue(value)
                logger.debug("[UIA] SetValue: %s = %r", runtime_id, value[:50])
                return True
        except Exception as e:
            logger.warning("[UIA] set_value failed %s: %s", runtime_id, e)
        return False

    def focus(self, runtime_id: str) -> bool:
        """Focus element by runtime ID."""
        try:
            uia = self._get_uia()
            if not uia:
                return False
            el = self._find_by_runtime_id(uia, runtime_id)
            if el:
                el.SetFocus()
                return True
        except Exception as e:
            logger.debug("[UIA] focus failed: %s", e)
        return False

    def get_value(self, runtime_id: str) -> Optional[str]:
        """Read current value of input element."""
        try:
            uia = self._get_uia()
            if not uia:
                return None
            el = self._find_by_runtime_id(uia, runtime_id)
            if el:
                pattern = el.GetCurrentPattern(_UIA_VALUE_PATTERN)
                if pattern:
                    return pattern.CurrentValue
        except Exception:
            pass
        return None

    def click(self, element: UIElement) -> ActionResult:
        """Compatibility wrapper for router-style callers."""
        if element.runtime_id and self.invoke(element.runtime_id):
            return ok(self.name, "invoked")

        target = self._find_element(element)
        if target is None:
            return fail(self.name, "UIA element not found")
        try:
            target.GetCurrentPattern(_UIA_INVOKE_PATTERN).Invoke()
            return ok(self.name, "invoked")
        except Exception as exc:
            try:
                target.SetFocus()
                return ok(self.name, "focused")
            except Exception:
                return fail(self.name, f"UIA click failed: {exc}")

    def type_text(self, element: UIElement, text: str) -> ActionResult:
        """Compatibility wrapper for router-style callers."""
        if element.runtime_id and self.set_value(element.runtime_id, text):
            return ok(self.name, "value set")

        target = self._find_element(element)
        if target is None:
            return fail(self.name, "UIA element not found")
        try:
            target.GetCurrentPattern(_UIA_VALUE_PATTERN).SetValue(text)
            return ok(self.name, "value set")
        except Exception as exc:
            return fail(self.name, f"UIA set value failed: {exc}")

    def _get_uia(self):
        try:
            import comtypes.client
            import comtypes.gen

            return comtypes.client.CreateObject(
                "{ff48dba4-60ef-4201-aa87-54103eef594e}",
                interface=comtypes.gen.UIAutomationClient.IUIAutomation,
            )
        except Exception as e:
            logger.warning("[UIA] Cannot create UIA: %s", e)
            return None

    def _find_by_runtime_id(self, uia, runtime_id: str):
        """Find element by runtime ID string."""
        try:
            parts = [int(x) for x in runtime_id.split(".")]
            import comtypes

            rid_array = (comtypes.c_int * len(parts))(*parts)
            return uia.ElementFromHandleRuntimeId(rid_array)
        except Exception:
            pass
        return None

    def _find_element(self, element: UIElement):
        """Best-effort compatibility lookup by automation ID or window handle."""
        try:
            uia = self._get_uia()
            if not uia:
                return None
            root = uia.ElementFromHandle(element.hwnd) if element.hwnd else uia.GetRootElement()
            if element.automation_id:
                condition = uia.CreatePropertyCondition(30011, element.automation_id)
                found = root.FindFirst(4, condition)
                if found:
                    return found
            return root
        except Exception:
            return None
