from __future__ import annotations

from agent.hands.engines.base import ok
from rawvision.capture.process_monitor import ProcessInfo
from rawvision.output.schema import AppType, ElementRole, ElementSource, UIElement


def test_app_classifier_routes_by_process_and_element():
    from agent.hands.router import AppClassifier

    classifier = AppClassifier()

    chrome = ProcessInfo(app_type=AppType.CHROME, cdp_available=True)
    terminal = ProcessInfo(app_type=AppType.TERMINAL)
    win32 = ProcessInfo(app_type=AppType.WIN32)
    cdp_element = UIElement(
        name="Search",
        role=ElementRole.INPUT,
        source=ElementSource.CDP,
        cdp_node_id=10,
    )
    uia_element = UIElement(
        name="OK",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        automation_id="ok",
    )

    assert classifier.route_for("click", cdp_element, chrome) == "cdp"
    assert classifier.route_for("run_command", None, terminal) == "terminal"
    assert classifier.route_for("click", uia_element, win32) == "uia"
    assert classifier.route_for("click", None, ProcessInfo(app_type=AppType.GAME)) == "sendinput"


def test_action_router_returns_engine_instance():
    from agent.hands.router import ActionRouter

    engines = {"cdp": object(), "sendinput": object()}
    router = ActionRouter(engines=engines)
    chrome = ProcessInfo(app_type=AppType.CHROME, cdp_available=True)
    element = UIElement(
        name="Link",
        role=ElementRole.LINK,
        source=ElementSource.CDP,
        cdp_node_id=5,
    )

    assert router.engine_for("click", element, chrome) is engines["cdp"]
    assert router.engine_for("click", None, ProcessInfo(app_type=AppType.UNKNOWN)) is engines["sendinput"]


def test_app_classifier_terminal_only_claims_commands():
    from agent.hands.router import AppClassifier

    classifier = AppClassifier()
    process = ProcessInfo(app_type=AppType.TERMINAL)

    assert classifier.route_for("run_command", None, process) == "terminal"
    assert classifier.route_for("type_text", None, process) == "sendinput"


def test_hands_controller_delegates_click_and_type():
    from agent.hands.router import HandsController

    calls = []

    class FakeRouter:
        def engine_for(self, action, element=None, process_info=None):
            calls.append(("route", action, element.name if element else None))
            return self

        def click(self, element):
            calls.append(("click", element.name))
            return ok("fake", "clicked")

        def type_text(self, element, text):
            calls.append(("type", element.name, text))
            return ok("fake", "typed")

    element = UIElement(name="Search", role=ElementRole.INPUT)
    controller = HandsController(router=FakeRouter())

    assert controller.click(element).success is True
    assert controller.type_text(element, "hello").success is True
    assert calls == [
        ("route", "click", "Search"),
        ("click", "Search"),
        ("route", "type_text", "Search"),
        ("type", "Search", "hello"),
    ]


def test_sendinput_type_text_uses_controller_signature():
    from agent.hands.engines.sendinput_engine import SendInputEngine

    sent = []

    engine = SendInputEngine()
    engine_char = "agent.hands.engines.sendinput_engine._send_unicode_char"

    import pytest

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine_char, lambda char: sent.append(char) or True)
        element = UIElement(name="Fallback", role=ElementRole.INPUT)
        result = engine.type_text(element, "ok")

    assert result.success is True
    assert sent == ["o", "k"]
