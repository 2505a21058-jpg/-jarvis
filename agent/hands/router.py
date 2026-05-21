"""
agent/hands/router.py

Route high-level actions to the best Hands engine.
"""

from __future__ import annotations

from typing import Optional

from agent.hands.engines import (
    CDPEngine,
    SendInputEngine,
    TerminalEngine,
    UIAEngine,
    WinApiEngine,
)
from agent.hands.engines.base import ActionResult, fail
from rawvision.capture.process_monitor import ProcessInfo
from rawvision.output.schema import AppType, ElementSource, UIElement


class AppClassifier:
    """Classify actions into Hands engine route names."""

    def route_for(
        self,
        action: str,
        element: Optional[UIElement] = None,
        process_info: Optional[ProcessInfo] = None,
    ) -> str:
        app_type = process_info.app_type if process_info else AppType.UNKNOWN

        if action == "run_command":
            return "terminal"

        if app_type in (AppType.CHROME, AppType.ELECTRON):
            if element and (element.source is ElementSource.CDP or element.cdp_node_id is not None):
                return "cdp"

        if app_type is AppType.GAME:
            return "sendinput"

        if element and (element.automation_id or element.runtime_id):
            return "uia"

        if element and element.hwnd:
            return "winapi"

        return "sendinput"


class ActionRouter:
    """Resolve a route name to a concrete engine instance."""

    def __init__(
        self,
        classifier: Optional[AppClassifier] = None,
        engines: Optional[dict[str, object]] = None,
    ):
        self.classifier = classifier or AppClassifier()
        self.engines = engines or {
            "cdp": CDPEngine(),
            "uia": UIAEngine(),
            "winapi": WinApiEngine(),
            "terminal": TerminalEngine(),
            "sendinput": SendInputEngine(),
        }

    def engine_for(
        self,
        action: str,
        element: Optional[UIElement] = None,
        process_info: Optional[ProcessInfo] = None,
    ):
        route = self.classifier.route_for(action, element, process_info)
        return self.engines.get(route) or self.engines["sendinput"]


class HandsController:
    """Single public API for routed computer actions."""

    def __init__(self, router: Optional[ActionRouter] = None):
        self.router = router or ActionRouter()

    def click(
        self,
        element: UIElement,
        process_info: Optional[ProcessInfo] = None,
    ) -> ActionResult:
        engine = self.router.engine_for("click", element, process_info)
        if not hasattr(engine, "click"):
            return fail("hands", "engine cannot click")
        return engine.click(element)

    def type_text(
        self,
        element: UIElement,
        text: str,
        process_info: Optional[ProcessInfo] = None,
    ) -> ActionResult:
        engine = self.router.engine_for("type_text", element, process_info)
        if not hasattr(engine, "type_text"):
            return fail("hands", "engine cannot type")
        return engine.type_text(element, text)

    def run_command(
        self,
        command: str,
        process_info: Optional[ProcessInfo] = None,
    ) -> ActionResult:
        engine = self.router.engine_for("run_command", None, process_info)
        if not hasattr(engine, "run_command"):
            return fail("hands", "engine cannot run commands")
        return engine.run_command(command)
