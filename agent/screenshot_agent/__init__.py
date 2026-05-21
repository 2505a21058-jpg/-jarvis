"""
agent/screenshot_agent/__init__.py

ScreenshotAgent — a self-contained screenshot-only computer use agent
that mirrors Claude Computer Use's perceive→plan→act→verify loop.

Powered by local models: mss (screenshot), PaddleOCR (text detection),
and LLaVA/Gemma3 vision (planning, verification).

Acts as a fallback when UIA/DOM/accessibility layers are unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.screenshot_agent._perception import perceive, ScreenRepr
from agent.screenshot_agent._planner import plan, PlannedAction
from agent.screenshot_agent._executor import execute as execute_action, ActionResult
from agent.screenshot_agent._verifier import verify as verify_action

logger = logging.getLogger("jarvis.screenshot_agent")

_DEFAULT_MAX_STEPS = 15
_STEP_DELAY = 0.5


@dataclass
class StepRecord:
    index: int
    action: str
    success: bool
    message: str
    verified: bool
    verify_msg: str
    perception_ms: float = 0.0


@dataclass
class ScreenshotResult:
    success: bool
    task: str
    steps_taken: int
    final_reason: str
    trace: list[dict] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)


class ScreenshotAgent:
    def __init__(
        self,
        max_steps: int = _DEFAULT_MAX_STEPS,
        step_delay: float = _STEP_DELAY,
        zoom_enabled: bool = True,
    ):
        self.max_steps = max(1, int(max_steps))
        self.step_delay = max(0.0, float(step_delay))
        self.zoom_enabled = zoom_enabled

    def run(self, task: str) -> ScreenshotResult:
        history: list[dict] = []
        steps: list[StepRecord] = []
        import time

        for index in range(1, self.max_steps + 1):
            screen = perceive()
            if screen is None:
                return ScreenshotResult(
                    success=False,
                    task=task,
                    steps_taken=index,
                    final_reason="Screenshot capture unavailable (mss not installed?)",
                    steps=steps,
                )

            action = plan(task, screen, history)

            if action.action == "done":
                steps.append(StepRecord(index=index, action="done", success=True, message=action.reason or "completed", verified=True, verify_msg=""))
                history.append({"action": "done", "success": True, "reason": action.reason})
                return ScreenshotResult(
                    success=True,
                    task=task,
                    steps_taken=index,
                    final_reason=action.reason or "completed",
                    trace=[{"action": self._name_for(h), "success": h.get("success"), "msg": self._msg_for(h)} for h in history],
                    steps=steps,
                )

            if action.action == "fail":
                steps.append(StepRecord(index=index, action="fail", success=False, message=action.reason or "failed", verified=True, verify_msg=""))
                history.append({"action": "fail", "success": False, "reason": action.reason})
                return ScreenshotResult(
                    success=False,
                    task=task,
                    steps_taken=index,
                    final_reason=action.reason or "Agent reported failure",
                    trace=[{"action": self._name_for(h), "success": h.get("success"), "msg": self._msg_for(h)} for h in history],
                    steps=steps,
                )

            if action.action == "zoom" and self.zoom_enabled:
                x1, y1, x2, y2 = action.x1 or 0, action.y1 or 0, action.x2 or 0, action.y2 or 0
                if x2 > x1 and y2 > y1:
                    logger.info("Zooming into region (%d,%d)-(%d,%d)", x1, y1, x2, y2)
                    zoomed = perceive(zoom_region=(x1, y1, x2, y2))
                    if zoomed:
                        screen = zoomed
                        action = plan(task, screen, history)
                        if action.action == "zoom":
                            action.action = "wait"
                            action.seconds = 1.0

            result = execute_action(
                action.action,
                x=action.x,
                y=action.y,
                text=action.text,
                keys=action.keys,
                direction=action.direction,
                amount=action.amount,
                seconds=action.seconds,
            )

            verified, verify_msg = verify_action(
                action.action,
                result.action,
                result.before_b64,
                result.after_b64,
                result.success,
            )

            if not verified and result.success:
                logger.warning("Step %d passed executor but failed verification: %s", index, verify_msg)

            steps.append(StepRecord(
                index=index,
                action=action.action,
                success=result.success,
                message=result.message,
                verified=verified,
                verify_msg=verify_msg,
                perception_ms=screen.capture_ms,
            ))

            history.append({
                "action": action.action,
                "success": result.success,
                "message": result.message,
                "verified": verified,
            })

            if self.step_delay:
                time.sleep(self.step_delay)

        reason = f"Reached max steps ({self.max_steps}) without completing"
        return ScreenshotResult(
            success=False,
            task=task,
            steps_taken=self.max_steps,
            final_reason=reason,
            trace=[{"action": self._name_for(h), "success": h.get("success"), "msg": self._msg_for(h)} for h in history],
            steps=steps,
        )

    def single_action(self, action_type: str, params: dict[str, Any]) -> ActionResult:
        screen = perceive()
        if screen is None:
            return ActionResult("screenshot", False, "Screenshot unavailable")

        task = params.get("task") or params.get("element") or action_type
        pa = plan(task, screen, [])
        return execute_action(
            pa.action if pa.action != "done" else "click",
            x=pa.x or params.get("x"),
            y=pa.y or params.get("y"),
            text=pa.text or params.get("text"),
            keys=pa.keys or params.get("keys"),
        )

    @staticmethod
    def _name_for(h: dict) -> str:
        return str(h.get("action") or h.get("type") or "?")

    @staticmethod
    def _msg_for(h: dict) -> str:
        return str(h.get("message") or h.get("reason") or "")
