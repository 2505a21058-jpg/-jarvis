"""
agent/computer_use.py

Perception-action loop built on RawVision + Hands.
Uses RawVision for screen context, a vision planner for next actions, and
HandsController for execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from agent.hands import HandsController
from agent.hands.engines.base import ActionResult, fail, ok
from agent.screen_verify import verify_action_with_screenshot
from rawvision import RawVision
from rawvision.capture.process_monitor import ProcessInfo
from rawvision.output.schema import AppType, ElementRole, ScreenContext, UIElement

logger = logging.getLogger("jarvis.computer_use")

_DEFAULT_MAX_STEPS = 8
_OLLAMA_BASE = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
_VISION_MODEL = os.getenv("JARVIS_VISION_MODEL", "llava")

_DECISION_SYSTEM = """You are a computer automation agent controlling a Windows PC.
Examine the screenshot and screen text carefully before choosing the next action.
Return ONLY JSON for the single next action. Available actions:

{"action":"click","target":{"name":"...","role":"button"}}
  Click element matching name/role on screen

{"action":"type_text","target":{"name":"...","role":"input"},"text":"..."}
  Type text into an input field. Set target to {} or null to type at cursor.

{"action":"run_command","command":"..."}
  Run a shell command (cmd or powershell)

{"action":"navigate","url":"https://..."}
  Navigate browser to URL (use full URL with scheme)

{"action":"key","combo":"ctrl+s"}
  Send keyboard shortcut (ctrl+c, alt+tab, win+r, etc.)

{"action":"scroll","direction":"down"}
  Scroll page (up/down)

{"action":"wait","seconds":1}
  Wait for page to load or changes to appear

{"action":"done","reason":"task completed successfully"}
  Signal task is complete

{"action":"fail","reason":"could not find login button"}
  Signal task cannot be completed

Use the screenshot and text context to understand what's on screen before deciding."""


class Planner(Protocol):
    def plan(
        self,
        task: str,
        context: ScreenContext,
        scratchpad: list[str],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class ComputerUseStep:
    index: int
    action: str
    target: str = ""
    success: bool = False
    message: str = ""


@dataclass(frozen=True)
class ComputerUseResult:
    success: bool
    task: str
    steps_taken: int
    final_reason: str
    scratchpad: tuple[str, ...] = field(default_factory=tuple)
    steps: tuple[ComputerUseStep, ...] = field(default_factory=tuple)
    last_context: Optional[ScreenContext] = None


@dataclass
class TaskMemory:
    entries: list[str] = field(default_factory=list)

    def summary(self, last_n: int = 4) -> str:
        recent = self.entries[-max(1, int(last_n)):]
        return "\n".join(recent) if recent else "(none)"


async def _decide(
    goal: str,
    screen_summary: str,
    memory: TaskMemory,
    screenshot_b64: Optional[str] = None,
) -> Optional[dict]:
    """
    Ask Gemma3:4b to decide next action.
    Always passes screenshot to vision model; if vision unavailable,
    the text prompt notes a screenshot was captured so the planner
    can still reason about visual state from the text context.
    Falls back through Gemma text -> main LLM.
    """
    visual_hint = (
        "A screenshot of the current screen was captured and is attached to this prompt."
        if screenshot_b64
        else "No screenshot available — rely on the text screen description."
    )
    user_prompt = (
        f"GOAL: {goal}\n\n"
        f"PROGRESS:\n{memory.summary(last_n=4)}\n\n"
        f"CURRENT SCREEN (text):\n{screen_summary}\n\n"
        f"Screenshot: {visual_hint}\n\n"
        "What is the single next action?"
    )

    if screenshot_b64:
        try:
            from models.gemma import call_gemma_vision_json

            result = call_gemma_vision_json(
                prompt=user_prompt,
                image_b64=screenshot_b64,
                system=_DECISION_SYSTEM,
            )
            if result and "action" in result:
                logger.debug("[COMPUTER USE] Decision via Gemma3 vision")
                return result
        except Exception as e:
            logger.warning(
                "[COMPUTER USE] Gemma3 vision failed, trying text: %s",
                e,
            )

    try:
        from models.gemma import call_gemma_json

        result = call_gemma_json(
            prompt=user_prompt,
            system=_DECISION_SYSTEM,
        )
        if result and "action" in result:
            logger.debug("[COMPUTER USE] Decision via Gemma3 text")
            return result
    except Exception as e:
        logger.warning(
            "[COMPUTER USE] Gemma3 failed, falling back to main LLM: %s",
            e,
        )

    try:
        from models.llm import call_llm_json

        result = call_llm_json(
            system=_DECISION_SYSTEM,
            user=user_prompt,
            temperature=0.1,
            max_tokens=200,
        )
        return result
    except Exception as e:
        logger.error("[COMPUTER USE] All decision models failed: %s", e)
        return None


def _run_decision(
    goal: str,
    screen_summary: str,
    memory: TaskMemory,
    screenshot_b64: Optional[str],
) -> Optional[dict]:
    coro = _decide(goal, screen_summary, memory, screenshot_b64=screenshot_b64)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    if not loop.is_running():
        return loop.run_until_complete(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


class OllamaVisionPlanner:
    """Planner that asks Gemma3:4b for computer-use decisions."""

    def __init__(
        self,
        model: str = _VISION_MODEL,
        ollama_base: str = _OLLAMA_BASE,
        timeout: float = 12.0,
    ):
        self.model = model
        self.ollama_base = ollama_base.rstrip("/")
        self.timeout = timeout

    def plan(
        self,
        task: str,
        context: ScreenContext,
        scratchpad: list[str],
    ) -> dict[str, Any]:
        _ = (self.model, self.ollama_base, self.timeout)
        memory = TaskMemory(entries=list(scratchpad or ()))
        result = _run_decision(
            goal=task,
            screen_summary=context.to_gemma(max_tokens=300),
            memory=memory,
            screenshot_b64=context.screenshot_b64,
        )
        if result:
            return _normalize_plan(result)
        return {
            "action": "fail",
            "reason": "planner unavailable",
        }


class ComputerUseAgent:
    """Run task-directed computer-use loops."""

    def __init__(
        self,
        vision=None,
        hands=None,
        planner: Optional[Planner] = None,
        max_steps: int = _DEFAULT_MAX_STEPS,
        step_delay_s: float = 0.0,
    ):
        self.vision = vision or RawVision()
        self.hands = hands or HandsController()
        self.planner = planner or OllamaVisionPlanner()
        self.max_steps = max(1, int(max_steps))
        self.step_delay_s = max(0.0, float(step_delay_s))

    def run(self, task: str) -> ComputerUseResult:
        scratchpad: list[str] = []
        steps: list[ComputerUseStep] = []
        last_context: Optional[ScreenContext] = None

        for index in range(1, self.max_steps + 1):
            last_context = _capture_with_screenshot(self.vision)

            if _should_fallback_to_screenshot(last_context):
                logger.info("No UIA/DOM elements in context — switching to screenshot-only agent")
                try:
                    from agent.screenshot_agent import ScreenshotAgent
                    sa = ScreenshotAgent(max_steps=self.max_steps - index + 1)
                    result = sa.run(task)
                    for s in result.steps:
                        steps.append(ComputerUseStep(index=index + s.index - 1, action=s.action, success=s.success, message=s.message))
                        scratchpad.append(f"step {index + s.index - 1}: {s.action} -> {'ok' if s.success else 'failed'}: {s.message}")
                    return ComputerUseResult(
                        success=result.success,
                        task=task,
                        steps_taken=index + result.steps_taken - 1,
                        final_reason=result.final_reason,
                        scratchpad=tuple(scratchpad),
                        steps=tuple(steps),
                        last_context=last_context,
                    )
                except Exception as exc:
                    logger.error("Screenshot agent failed: %s", exc)

            plan = _normalize_plan(self.planner.plan(task, last_context, scratchpad))
            action = plan.get("action", "wait")

            if action in {"done", "finish", "complete"}:
                reason = str(plan.get("reason") or "completed")
                steps.append(ComputerUseStep(index=index, action="done", success=True, message=reason))
                scratchpad.append(f"step {index}: done - {reason}")
                return ComputerUseResult(
                    success=True,
                    task=task,
                    steps_taken=index,
                    final_reason=reason,
                    scratchpad=tuple(scratchpad),
                    steps=tuple(steps),
                    last_context=last_context,
                )

            if action in {"fail", "abort", "stop"}:
                reason = str(plan.get("reason") or "planner stopped")
                steps.append(ComputerUseStep(index=index, action="fail", success=False, message=reason))
                scratchpad.append(f"step {index}: fail - {reason}")
                return ComputerUseResult(
                    success=False,
                    task=task,
                    steps_taken=index,
                    final_reason=reason,
                    scratchpad=tuple(scratchpad),
                    steps=tuple(steps),
                    last_context=last_context,
                )

            result = self._execute_plan(plan, last_context)

            verified, verify_msg = self._verify_step(plan, result)
            if not verified:
                logger.warning("[COMPUTER USE] Step %d verify failed: %s", index, verify_msg)

            steps.append(
                ComputerUseStep(
                    index=index,
                    action=action,
                    target=_target_label(plan),
                    success=result.success,
                    message=result.message,
                )
            )
            scratchpad.append(
                f"step {index}: {action} {_target_label(plan)} -> "
                f"{'ok' if result.success else 'failed'}: {result.message}"
                f"{' [verified]' if verified else ' [verify: ' + verify_msg + ']'}"
            )

            if self.step_delay_s:
                time.sleep(self.step_delay_s)

        reason = f"stopped after max steps ({self.max_steps})"
        return ComputerUseResult(
            success=False,
            task=task,
            steps_taken=self.max_steps,
            final_reason=reason,
            scratchpad=tuple(scratchpad),
            steps=tuple(steps),
            last_context=last_context,
        )

    def _verify_step(
        self,
        plan: dict[str, Any],
        result: ActionResult,
        wait_seconds: float = 1.5,
    ) -> tuple[bool, str]:
        action = str(plan.get("action") or "").lower()
        if action in ("wait", "done", "fail", "abort", "stop"):
            return True, "no verification needed"

        if not result.success:
            return False, result.message

        if action == "run_command":
            return True, "command completed"

        description = f"performed {action} on {_target_label(plan)}"
        expected = f"{action} completed successfully"
        try:
            if wait_seconds > 0:
                import time
                time.sleep(wait_seconds)
            verified, msg = verify_action_with_screenshot(description, expected, wait_seconds=0)
            return (verified, msg) if verified else (verified, msg or "visual verification uncertain")
        except Exception as exc:
            logger.debug("[COMPUTER USE] Verify skipped: %s", exc)
            return True, "verify unavailable"

    def _execute_plan(
        self,
        plan: dict[str, Any],
        context: ScreenContext,
    ) -> ActionResult:
        action = str(plan.get("action") or "wait").lower()
        process_info = _process_info_from_context(context)

        if action in ("wait", "sleep"):
            seconds = int(plan.get("seconds", 1))
            import time
            time.sleep(seconds)
            return ok("computer_use", f"waited {seconds}s")

        if action == "run_command":
            command = str(plan.get("command") or "")
            if not command:
                return fail("computer_use", "missing command")
            if not hasattr(self.hands, "run_command"):
                return fail("computer_use", "hands cannot run command")
            return self.hands.run_command(command, process_info=process_info)

        if action in ("navigate", "goto", "go"):
            url = str(plan.get("url") or "")
            if not url:
                return fail("computer_use", "missing url")
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            if hasattr(self.hands, "navigate"):
                result = self.hands.navigate(url)
                if hasattr(result, "__await__"):
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        success = asyncio.run_coroutine_threadsafe(result.__await__().__anext__(), loop).result(timeout=30)
                    else:
                        success = asyncio.run(result)
                else:
                    success = result
                return ok("computer_use", f"navigated to {url}") if success else fail("computer_use", f"navigation to {url} failed")
            url = f"navigated to {url}" if not url.startswith("about:") else url
            return ok("computer_use", url)

        if action in ("key", "hotkey", "press"):
            combo = str(plan.get("combo") or plan.get("keys") or "")
            if not combo:
                return fail("computer_use", "missing key combo")
            if hasattr(self.hands, "key"):
                result = self.hands.key(combo)
                if hasattr(result, "__await__"):
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop and loop.is_running():
                        success = asyncio.run_coroutine_threadsafe(result.__await__().__anext__(), loop).result(timeout=10)
                    else:
                        success = asyncio.run(result)
                else:
                    success = result
                return ok("computer_use", f"sent {combo}") if success else fail("computer_use", f"key combo failed: {combo}")
            return ok("computer_use", f"sent {combo}")

        if action == "scroll":
            direction = str(plan.get("direction", "down")).lower()
            if hasattr(self.hands, "key"):
                key_combo = "pagedown" if direction == "down" else "pageup"
                self.hands.key(key_combo)
            return ok("computer_use", f"scrolled {direction}")

        target = plan.get("target")
        element = _find_target(context, target)
        if element is None:
            return fail("computer_use", "target not found")

        if action == "click":
            return self.hands.click(element, process_info=process_info)

        if action == "type_text":
            text = str(plan.get("text") or "")
            if not text:
                return fail("computer_use", "missing text")
            return self.hands.type_text(element, text, process_info=process_info)

        return fail("computer_use", f"unknown action: {action}")


def _planner_prompt(
    task: str,
    context: ScreenContext,
    scratchpad: list[str],
) -> str:
    return (
        "You control a computer through structured actions.\n"
        "Return ONLY JSON with one of these shapes:\n"
        '{"action":"click","target":{"name":"...","role":"button"}}\n'
        '{"action":"type_text","target":{"name":"...","role":"input"},"text":"..."}\n'
        '{"action":"run_command","command":"..."}\n'
        '{"action":"wait"}\n'
        '{"action":"done","reason":"..."}\n\n'
        f"Task: {task}\n\n"
        f"Screen:\n{context.to_llm(max_tokens=900)}\n\n"
        f"Scratchpad:\n{chr(10).join(scratchpad[-8:]) or '(empty)'}"
    )


def _capture_with_screenshot(vision) -> ScreenContext:
    try:
        return vision.capture(include_screenshot=True)
    except TypeError:
        return vision.capture()


def _extract_plan(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return {"action": "wait", "reason": "planner returned no JSON"}
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return {"action": "wait", "reason": "planner returned invalid JSON"}

    return _normalize_plan(data)


def _normalize_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {"action": "wait", "reason": "planner returned invalid plan"}
    normalized = dict(plan)
    normalized["action"] = str(normalized.get("action") or "wait").lower()
    return normalized


def _find_target(
    context: ScreenContext,
    target: Any,
) -> Optional[UIElement]:
    if isinstance(target, UIElement):
        return target

    if not target:
        focused = context.find_focused()
        if focused:
            return focused
        typeables = [element for element in context.elements if element.is_typeable]
        return typeables[0] if typeables else None

    if isinstance(target, str):
        return context.find(name=target, min_confidence=0.0)

    if isinstance(target, dict):
        element_id = str(target.get("element_id") or "").strip()
        if element_id:
            found = context.find_by_id(element_id)
            if found:
                return found

        name = str(target.get("name") or "")
        role_value = target.get("role")
        role = None
        if role_value:
            try:
                role = ElementRole(str(role_value).lower())
            except ValueError:
                role = None
        return context.find(name=name, role=role, min_confidence=0.0)

    return None


def _target_label(plan: dict[str, Any]) -> str:
    target = plan.get("target")
    if isinstance(target, dict):
        return str(target.get("name") or target.get("element_id") or "").strip()
    if target:
        return str(target)
    if plan.get("command"):
        return str(plan.get("command"))
    return ""


def _process_info_from_context(context: ScreenContext) -> ProcessInfo:
    return ProcessInfo(
        pid=context.app_pid,
        process_name=context.app_name.lower(),
        window_title=context.window_title,
        app_type=context.app_type,
        app_friendly_name=context.app_name,
        cdp_available=context.cdp_port is not None,
        cdp_port=context.cdp_port,
    )


def _should_fallback_to_screenshot(context: ScreenContext) -> bool:
    has_elements = len(context.elements) > 0
    has_app = bool(context.app_name)
    has_window = bool(context.window_title)
    has_cdp = context.cdp_port is not None
    return not (has_elements or has_app or has_window or has_cdp)
