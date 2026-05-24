from __future__ import annotations

from agent.hands.engines.base import ok
from rawvision.output.schema import ElementRole, ElementSource, ScreenContext, UIElement


def test_computer_use_clicks_then_finishes():
    from agent.computer_use import ComputerUseAgent

    button = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        is_clickable=True,
    )
    contexts = [
        ScreenContext(app_name="Test", elements=[button]),
        ScreenContext(app_name="Test", elements=[]),
    ]
    actions = [
        {"action": "click", "target": {"name": "Save", "role": "button"}},
        {"action": "done", "reason": "saved"},
    ]
    calls = []

    class FakeVision:
        def capture(self):
            return contexts.pop(0)

    class FakeHands:
        def click(self, element, process_info=None):
            calls.append(("click", element.name, process_info.app_type.value))
            return ok("fake", "clicked")

    class FakePlanner:
        def plan(self, task, context, scratchpad):
            assert task == "save the file"
            assert isinstance(scratchpad, list)
            return actions.pop(0)

    result = ComputerUseAgent(
        vision=FakeVision(),
        hands=FakeHands(),
        planner=FakePlanner(),
        max_steps=3,
    ).run("save the file")

    assert result.success is True
    assert result.steps_taken == 2
    assert result.final_reason == "saved"
    assert calls == [("click", "Save", "unknown")]
    assert "clicked" in result.scratchpad[-2]


def test_default_computer_use_uses_gemma3_vision_with_screenshot(monkeypatch):
    from agent.computer_use import ComputerUseAgent

    button = UIElement(
        name="Save",
        role=ElementRole.BUTTON,
        source=ElementSource.UIA,
        is_clickable=True,
    )
    context = ScreenContext(app_name="Test", elements=[button], screenshot_b64="image-b64")
    capture_calls = []
    decisions = [
        {"action": "click", "target": {"name": "Save", "role": "button"}},
        {"action": "done", "reason": "saved"},
    ]
    gemma_calls = []
    hand_calls = []

    class FakeVision:
        def capture(self, include_screenshot=False):
            capture_calls.append(include_screenshot)
            return context

    class FakeHands:
        def click(self, element, process_info=None):
            hand_calls.append(("click", element.name))
            return ok("fake", "clicked")

    def fake_gemma_vision_json(prompt, image_b64, system="", retries=2):
        gemma_calls.append((prompt, image_b64, system))
        return decisions.pop(0)

    monkeypatch.setattr(
        "models.gemma.call_gemma_vision_json",
        fake_gemma_vision_json,
    )

    result = ComputerUseAgent(
        vision=FakeVision(),
        hands=FakeHands(),
        max_steps=3,
    ).run("save the file")

    assert result.success is True
    assert capture_calls == [True, True]
    assert [call[1] for call in gemma_calls] == ["image-b64", "image-b64"]
    assert hand_calls == [("click", "Save")]


def test_computer_use_types_into_focused_or_named_element():
    from agent.computer_use import ComputerUseAgent

    input_el = UIElement(
        name="Search",
        role=ElementRole.INPUT,
        source=ElementSource.CDP,
        cdp_node_id=55,
        is_typeable=True,
        is_focused=True,
    )
    calls = []

    class FakeVision:
        def capture(self):
            return ScreenContext(app_name="Chrome", app_type="chrome", elements=[input_el])

    class FakeHands:
        def type_text(self, element, text, process_info=None):
            calls.append((element.name, text, process_info.app_type.value))
            return ok("fake", "typed")

    class FakePlanner:
        def __init__(self):
            self.calls = 0

        def plan(self, task, context, scratchpad):
            self.calls += 1
            if self.calls == 1:
                return {"action": "type_text", "text": "rawvision"}
            return {"action": "done", "reason": "typed"}

    result = ComputerUseAgent(FakeVision(), FakeHands(), FakePlanner(), max_steps=3).run("search")

    assert result.success is True
    assert calls == [("Search", "rawvision", "chrome")]


def test_computer_use_replans_after_failed_action():
    from agent.computer_use import ComputerUseAgent

    class FakeVision:
        def capture(self):
            return ScreenContext(app_name="Test", elements=[])

    class FakeHands:
        pass

    class FakePlanner:
        def __init__(self):
            self.calls = 0

        def plan(self, task, context, scratchpad):
            self.calls += 1
            if self.calls == 1:
                return {"action": "click", "target": {"name": "Missing"}}
            return {"action": "done", "reason": "nothing to click"}

    planner = FakePlanner()
    result = ComputerUseAgent(FakeVision(), FakeHands(), planner, max_steps=3).run("click missing")

    assert result.success is True
    assert result.steps_taken == 2
    assert planner.calls == 2
    assert any("target not found" in item for item in result.scratchpad)


def test_computer_use_stops_at_max_steps():
    from agent.computer_use import ComputerUseAgent

    class FakeVision:
        def capture(self):
            return ScreenContext(app_name="Test")

    class FakePlanner:
        def plan(self, task, context, scratchpad):
            return {"action": "wait"}

    result = ComputerUseAgent(
        vision=FakeVision(),
        hands=object(),
        planner=FakePlanner(),
        max_steps=2,
    ).run("wait forever")

    assert result.success is False
    assert result.steps_taken == 2
    assert "max steps" in result.final_reason


def test_computer_use_can_stop_with_planner_failure():
    from agent.computer_use import ComputerUseAgent

    class FakeVision:
        def capture(self):
            return ScreenContext(app_name="Test")

    class FakePlanner:
        def plan(self, task, context, scratchpad):
            return {"action": "fail", "reason": "planner unavailable"}

    result = ComputerUseAgent(
        vision=FakeVision(),
        hands=object(),
        planner=FakePlanner(),
        max_steps=3,
    ).run("do a task")

    assert result.success is False
    assert result.steps_taken == 1
    assert result.final_reason == "planner unavailable"


def test_computer_use_rejects_planned_shell_command():
    from agent.computer_use import ComputerUseAgent

    class FakeVision:
        def capture(self):
            return ScreenContext(app_name="Terminal")

    class FakeHands:
        def __init__(self):
            self.commands = []

        def run_command(self, command, process_info=None):
            self.commands.append(command)
            return ok("fake", "ran command")

    class FakePlanner:
        def __init__(self):
            self.calls = 0

        def plan(self, task, context, scratchpad):
            self.calls += 1
            if self.calls == 1:
                return {"action": "run_command", "command": "whoami"}
            return {"action": "done", "reason": "command rejected"}

    hands = FakeHands()
    result = ComputerUseAgent(
        vision=FakeVision(),
        hands=hands,
        planner=FakePlanner(),
        max_steps=3,
    ).run("run a command")

    assert result.success is True
    assert hands.commands == []
    assert any("not allowed" in item.lower() for item in result.scratchpad)
