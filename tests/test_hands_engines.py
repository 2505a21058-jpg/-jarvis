from __future__ import annotations

from rawvision.output.schema import BoundingBox, ElementRole, UIElement


def test_cdp_engine_clicks_and_types_with_tab():
    from agent.hands.engines.cdp_engine import CDPEngine

    calls = []

    class FakeTab:
        async def click(self, node_id):
            calls.append(("click", node_id))
            return True

        async def type_text(self, text, node_id=None):
            calls.append(("type", text, node_id))
            return True

    element = UIElement(name="Search", role=ElementRole.INPUT, cdp_node_id=123)
    engine = CDPEngine(tab=FakeTab())

    assert engine.click(element).success is True
    assert engine.type_text(element, "hello").success is True
    assert calls == [("click", 123), ("type", "hello", 123)]


def test_uia_engine_invokes_and_sets_value(monkeypatch):
    from agent.hands.engines.uia_engine import UIAEngine

    calls = []

    class FakePattern:
        def Invoke(self):
            calls.append("invoke")

        def SetValue(self, value):
            calls.append(("set", value))

    class FakeElement:
        def GetCurrentPattern(self, pattern_id):
            calls.append(("pattern", pattern_id))
            return FakePattern()

    monkeypatch.setattr(UIAEngine, "_find_element", lambda self, element: FakeElement())
    element = UIElement(name="Name", role=ElementRole.INPUT, automation_id="name")
    engine = UIAEngine()

    assert engine.click(element).success is True
    assert engine.type_text(element, "Ada").success is True
    assert calls == [("pattern", 10000), "invoke", ("pattern", 10002), ("set", "Ada")]


def test_winapi_engine_sends_click_and_text_messages(monkeypatch):
    from agent.hands.engines.winapi_engine import BM_CLICK, WM_SETTEXT, WinApiEngine

    calls = []
    monkeypatch.setattr(
        "agent.hands.engines.winapi_engine._send_message",
        lambda hwnd, msg, wparam=0, lparam=0: calls.append((hwnd, msg, wparam, lparam)) or 1,
    )

    element = UIElement(name="OK", role=ElementRole.BUTTON, hwnd=500)
    engine = WinApiEngine()

    assert engine.click(element).success is True
    assert engine.type_text(element, "hello").success is True
    assert calls == [(500, BM_CLICK, 0, 0), (500, WM_SETTEXT, 0, "hello")]


def test_terminal_engine_runs_command():
    from agent.hands.engines.terminal_engine import TerminalEngine

    result = TerminalEngine().run_command("python -c \"print('hi')\"")

    assert result.success is True
    assert result.data["stdout"].strip() == "hi"


def test_sendinput_engine_clicks_element_center_with_dpi_correction(monkeypatch):
    from agent.hands.engines.sendinput_engine import SendInputEngine

    calls = []
    monkeypatch.setattr(
        "agent.hands.engines.sendinput_engine.dpi_correct",
        lambda point: type(point)(point.x // 2, point.y // 2),
    )
    monkeypatch.setattr(
        "agent.hands.engines.sendinput_engine._send_mouse_click",
        lambda x, y: calls.append((x, y)) or True,
    )

    element = UIElement(
        name="OK",
        role=ElementRole.BUTTON,
        bbox=BoundingBox(10, 20, 30, 40),
    )

    result = SendInputEngine().click(element)

    assert result.success is True
    assert calls == [(12, 20)]
