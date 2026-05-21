"""Tests for ScreenshotAgent — screenshot-only computer use fallback."""

from __future__ import annotations

from unittest.mock import patch, MagicMock, ANY

import pytest

from agent.screenshot_agent import ScreenshotAgent, StepRecord
from agent.screenshot_agent._perception import ScreenRepr, OCRText
from agent.screenshot_agent._planner import PlannedAction, plan
from agent.screenshot_agent._executor import execute, ActionResult
from agent.screenshot_agent._verifier import verify


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_repr():
    return ScreenRepr(
        screenshot_b64="fake_base64_png",
        width=1920,
        height=1080,
        ocr_texts=[
            OCRText(text="Submit", x=520, y=440, w=80, h=30, confidence=0.95),
            OCRText(text="Cancel", x=520, y=500, w=80, h=30, confidence=0.92),
        ],
        vision_description="A dialog with Submit and Cancel buttons.",
        capture_ms=45.0,
    )


@pytest.fixture
def agent():
    return ScreenshotAgent(max_steps=5, step_delay=0, zoom_enabled=True)


# ── Agent Loop ────────────────────────────────────────────────────────────────
# NOTE: patch the names imported in __init__.py, not the module-level names

@patch("agent.screenshot_agent.perceive")
@patch("agent.screenshot_agent.plan")
@patch("agent.screenshot_agent.execute_action")
@patch("agent.screenshot_agent.verify_action")
def test_agent_loop_completes_task(mock_verify, mock_execute, mock_plan, mock_perceive, agent, mock_repr):
    mock_perceive.return_value = mock_repr
    mock_plan.side_effect = [
        PlannedAction(action="click", x=520, y=440),
        PlannedAction(action="done", reason="submitted form"),
    ]
    mock_execute.return_value = ActionResult("click", True, "Clicked (520, 440)")
    mock_verify.return_value = (True, "Verified")

    result = agent.run("submit the form")
    assert result.success
    assert result.steps_taken == 2
    assert "submitted form" in result.final_reason


@patch("agent.screenshot_agent.perceive")
@patch("agent.screenshot_agent.plan")
def test_agent_fails_when_planner_says_fail(mock_plan, mock_perceive, agent, mock_repr):
    mock_perceive.return_value = mock_repr
    mock_plan.return_value = PlannedAction(action="fail", reason="cannot find the button")

    result = agent.run("click something")
    assert not result.success
    assert "cannot find" in result.final_reason


@patch("agent.screenshot_agent.perceive")
def test_agent_returns_error_when_screenshot_unavailable(mock_perceive, agent):
    mock_perceive.return_value = None
    result = agent.run("do something")
    assert not result.success
    assert "unavailable" in result.final_reason


@patch("agent.screenshot_agent.perceive")
@patch("agent.screenshot_agent.plan")
def test_agent_stops_at_max_steps(mock_plan, mock_perceive, agent, mock_repr):
    mock_perceive.return_value = mock_repr
    mock_plan.return_value = PlannedAction(action="click", x=100, y=100)

    with patch("agent.screenshot_agent.execute_action") as mock_exec:
        mock_exec.return_value = ActionResult("click", True, "clicked")
        with patch("agent.screenshot_agent.verify_action", return_value=(True, "ok")):
            result = agent.run("keep clicking")
    assert not result.success
    assert result.steps_taken == 5


# ── single_action ─────────────────────────────────────────────────────────────

@patch("agent.screenshot_agent.perceive")
@patch("agent.screenshot_agent.plan")
@patch("agent.screenshot_agent.execute_action")
def test_single_action_click(mock_execute, mock_plan, mock_perceive, agent, mock_repr):
    mock_perceive.return_value = mock_repr
    mock_plan.return_value = PlannedAction(action="click", x=520, y=440)
    mock_execute.return_value = ActionResult("click", True, "Clicked (520, 440)")

    result = agent.single_action("click", {"element": "Submit"})
    assert result.success
    assert "Clicked" in result.message


# ── Perception ────────────────────────────────────────────────────────────────

@patch("agent.screenshot_agent._perception._take_screenshot")
@patch("agent.screenshot_agent._perception._run_ocr")
@patch("agent.screenshot_agent._perception._describe_screen")
def test_perceive_returns_repr(mock_desc, mock_ocr, mock_ss):
    mock_ss.return_value = (b"fake_png_bytes", 1920, 1080)
    mock_ocr.return_value = [OCRText("hello", 100, 200, 50, 20, 0.95)]
    mock_desc.return_value = "A screen with text"

    from agent.screenshot_agent._perception import perceive
    repr = perceive()
    assert repr is not None
    assert repr.width == 1920
    assert repr.height == 1080
    assert len(repr.ocr_texts) == 1
    assert repr.ocr_texts[0].text == "hello"
    assert "screen with text" in repr.vision_description


# ── Planner ───────────────────────────────────────────────────────────────────

def test_planned_action_roundtrip():
    d = {"action": "click", "x": 100, "y": 200}
    pa = PlannedAction.from_dict(d)
    assert pa.action == "click"
    assert pa.x == 100
    assert pa.y == 200
    restored = pa.to_dict()
    assert restored["x"] == 100


def test_planned_action_clamps_unknown_action():
    d = {"action": "fly"}
    pa = PlannedAction.from_dict(d)
    assert pa.action == "wait"


def test_planned_action_handles_none_coords():
    d = {"action": "done", "reason": "finished"}
    pa = PlannedAction.from_dict(d)
    assert pa.action == "done"
    assert pa.x is None


@patch("agent.screenshot_agent._planner._call_vision_planner")
@patch("agent.screenshot_agent._planner._call_text_planner")
def test_plan_falls_back_to_text(mock_text, mock_vision, mock_repr):
    mock_vision.return_value = None
    mock_text.return_value = {"action": "click", "x": 100, "y": 200}

    pa = plan("click somewhere", mock_repr, [])
    assert pa.action == "click"
    assert pa.x == 100


@patch("agent.screenshot_agent._planner._call_vision_planner")
@patch("agent.screenshot_agent._planner._call_text_planner")
def test_plan_defaults_to_wait_when_all_fail(mock_text, mock_vision, mock_repr):
    mock_vision.return_value = None
    mock_text.return_value = None

    pa = plan("do something", mock_repr, [])
    assert pa.action == "wait"


# ── Executor ──────────────────────────────────────────────────────────────────

@patch("agent.screenshot_agent._executor._click")
def test_execute_click(mock_click):
    mock_click.return_value = True
    result = execute("click", x=100, y=200)
    assert result.success
    assert result.action == "click"
    mock_click.assert_called_once_with(100, 200)


@patch("agent.screenshot_agent._executor._type")
def test_execute_type(mock_type):
    mock_type.return_value = True
    result = execute("type", text="hello")
    assert result.success
    mock_type.assert_called_once_with("hello")


@patch("agent.screenshot_agent._executor._key")
def test_execute_key(mock_key):
    mock_key.return_value = True
    result = execute("key", keys="ctrl+s")
    assert result.success
    mock_key.assert_called_once_with("ctrl+s")


@patch("agent.screenshot_agent._executor._scroll")
def test_execute_scroll(mock_scroll):
    mock_scroll.return_value = True
    result = execute("scroll", direction="down", amount=3)
    assert result.success
    mock_scroll.assert_called_once_with("down", 3)


def test_execute_click_missing_coords():
    result = execute("click")
    assert not result.success


def test_execute_type_missing_text():
    result = execute("type")
    assert not result.success


def test_execute_unknown_action():
    result = execute("fly")
    assert not result.success


@patch("agent.screenshot_agent._executor._try_sendinput_click")
@patch("agent.screenshot_agent._executor._try_pyautogui_click")
def test_execute_falls_back_to_sendinput(mock_pg, mock_si):
    mock_pg.return_value = False
    mock_si.return_value = True
    result = execute("click", x=100, y=200)
    assert result.success
    mock_si.assert_called_once_with(100, 200)


# ── Verifier ──────────────────────────────────────────────────────────────────

def test_verify_skip_non_visual_actions():
    ok, msg = verify("done", "done", "before", "after", True)
    assert ok


def test_verify_no_after_screenshot():
    ok, msg = verify("click", "click", "before", "", True)
    assert ok
    assert "No after-screenshot" in msg


@patch("agent.screenshot_agent._verifier._pixel_diff")
def test_verify_relies_on_pixel_diff_when_vision_unavailable(mock_diff):
    mock_diff.return_value = 0.15
    with patch("agent.screenshot_agent._verifier._vision_verify", return_value=None):
        ok, msg = verify("click", "click", "before", "after", True)
    assert ok
    assert "15" in msg


@patch("agent.screenshot_agent._verifier._pixel_diff")
@patch("agent.screenshot_agent._verifier._vision_verify")
def test_verify_vision_takes_priority(mock_vision, mock_diff):
    mock_diff.return_value = 0.0
    mock_vision.return_value = True
    ok, msg = verify("click", "click", "before", "after", True)
    assert ok
    assert "Vision confirmed" in msg


@patch("agent.screenshot_agent._verifier._pixel_diff")
@patch("agent.screenshot_agent._verifier._vision_verify")
def test_verify_fails_on_vision_no(mock_vision, mock_diff):
    mock_diff.return_value = 0.05
    mock_vision.return_value = False
    ok, msg = verify("click", "click", "before", "after", True)
    assert not ok
    assert "Vision reported" in msg


# ── Integration: computer_control screenshot strategy ─────────────────────────

def test_computer_control_strategies_includes_screenshot():
    from skills.computer_control import _strategies_for_step
    from skills.computer_control import AutomationStep
    step = AutomationStep(action="skill", description="click", skill_name="gui_automate", params={"action": "click", "element": "OK"})
    strategies = _strategies_for_step(step)
    assert "screenshot" in strategies


# ── Integration: computer_use fallback detection ──────────────────────────────

def test_computer_use_fallback_checks_empty_context():
    from agent.computer_use import _should_fallback_to_screenshot
    from rawvision.output.schema import ScreenContext, AppType
    ctx = ScreenContext(elements=[], app_type=AppType.UNKNOWN, window_title="", app_name="")
    assert _should_fallback_to_screenshot(ctx) is True


def test_computer_use_no_fallback_when_app_name_present():
    from agent.computer_use import _should_fallback_to_screenshot
    from rawvision.output.schema import ScreenContext, AppType
    ctx = ScreenContext(elements=[], app_type=AppType.UNKNOWN, window_title="", app_name="Test")
    assert _should_fallback_to_screenshot(ctx) is False


def test_computer_use_no_fallback_when_elements_present():
    from agent.computer_use import _should_fallback_to_screenshot
    from rawvision.output.schema import ScreenContext, AppType, UIElement
    ctx = ScreenContext(
        elements=[UIElement(name="test", role="button", bbox=None, confidence=0.9)],
        app_type=AppType.WIN32,
        window_title="Test",
        app_name="test.exe",
    )
    assert _should_fallback_to_screenshot(ctx) is False


# ── Integration: Hands controller screenshot fallthrough ──────────────────────

@pytest.mark.asyncio
async def test_hands_controller_falls_through_to_screenshot():
    from agent.hands.controller import HandsController
    controller = HandsController()

    element = MagicMock()
    element.cdp_node_id = None
    element.runtime_id = None
    element.hwnd = None
    element.bbox = None
    element.name = "Submit"
    element.texts.side_effect = Exception("no texts")

    with patch("agent.screenshot_agent.execute_action") as mock_exec:
        mock_exec.return_value = ActionResult("click", True, "done")
        with patch("agent.screenshot_agent.plan") as mock_plan:
            mock_plan.return_value = PlannedAction(action="click", x=100, y=100)
            with patch("agent.screenshot_agent._perception._take_screenshot") as mock_ss:
                mock_ss.return_value = (b"fake_png", 100, 100)
                with patch("agent.screenshot_agent._perception._run_ocr", return_value=[]):
                    with patch("agent.screenshot_agent._perception._describe_screen", return_value="screen"):
                        result = await controller._click_async(element)
    assert result is True
