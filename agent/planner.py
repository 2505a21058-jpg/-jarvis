"""
agent/planner.py

Adaptive planner for Jarvis v2.
Features:
  - Conditional planning: only triggers for genuinely multi-step tasks
  - DAG-aware step definitions (depends_on)
  - Replanning: when a step fails, LLM generates a recovery plan
  - Plan validation before execution
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.context import build_plan_context
from models.llm import call_llm_cached


logger = logging.getLogger("jarvis.planner")


@dataclass
class Step:
    index: int
    skill_name: str
    description: str
    params: dict = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)
    output_key: Optional[str] = None
    result: Any = None
    success: bool = False
    error: Optional[str] = None


@dataclass
class Plan:
    goal: str
    steps: list[Step]
    context: dict = field(default_factory=dict)
    current_step: int = 0
    completed: bool = False
    failed: bool = False
    failure_reason: Optional[str] = None
    replan_count: int = 0


PLANNER_SYSTEM = """
You are a precise task planner for an AI assistant.
Decompose the given goal into a minimal sequence of steps using ONLY these skill names:
open_app, browse, type_text, search, system_command, respond, list_skills

Rules:
- Use the FEWEST steps possible. If 1 step suffices, use 1.
- Each step must have a unique output_key (snake_case)
- depends_on lists the step indices this step needs output from
- params can use {output_key} to reference previous step outputs
- Maximum 6 steps
- If the goal is a simple question or greeting, return 1 step with skill_name "respond"

Return ONLY valid JSON (no markdown, no explanation):
{
  "goal": "string",
  "steps": [
    {
      "index": 0,
      "skill_name": "string",
      "description": "string",
      "params": {},
      "depends_on": [],
      "output_key": "string"
    }
  ]
}
"""

REPLAN_SYSTEM = """
You are a recovery planner. A step in an AI task plan has failed.
Generate a revised plan that achieves the original goal while working around the failure.

Return ONLY valid JSON in the same format as the original plan.
Use the same skill names: open_app, browse, type_text, search, system_command, respond

Keep the revised plan minimal. Prefer alternative approaches over retrying the same failed step.
"""


_SIMPLE_TYPES = {"fast_chat", "respond", "list_skills", "teach_skill"}


def _needs_plan(decision: dict) -> bool:
    """
    Returns True only if this decision genuinely requires multi-step execution.
    Avoids unnecessary planner LLM call for simple tasks.
    """
    if decision.get("type") in _SIMPLE_TYPES:
        return False
    if not decision.get("requires_plan", False):
        return False
    if decision.get("name") and decision.get("parameters") and decision.get("type") == "skill":
        return False
    return True


def _validate_plan(plan_data: dict) -> tuple[bool, str]:
    """Validate parsed plan JSON before building Step objects."""
    steps = plan_data.get("steps", [])
    if not steps:
        return False, "Plan has no steps"
    if len(steps) > 6:
        return False, f"Plan has too many steps: {len(steps)}"

    try:
        indices = {step["index"] for step in steps}
    except KeyError:
        return False, "Plan step missing index"

    valid_skills = {"open_app", "browse", "type_text", "search", "system_command", "respond", "list_skills"}

    for step in steps:
        if "skill_name" not in step:
            return False, f"Step {step.get('index', '?')} missing skill_name"
        if step["skill_name"] not in valid_skills:
            return False, f"Step {step['index']} has unknown skill: {step['skill_name']}"
        for dep in step.get("depends_on", []):
            if dep not in indices:
                return False, f"Step {step['index']} depends on non-existent step {dep}"

    return True, ""


def plan(decision: dict, state, memory) -> Plan:
    """
    Convert a decision into an executable Plan.
    Only called when _needs_plan() returns True.
    """
    goal = decision.get("parameters", {}).get("raw_input", decision.get("name", "task"))

    hints = decision.get("hints", [])
    if hints and all("skill_name" in hint for hint in hints):
        try:
            steps = [
                Step(**{key: value for key, value in hint.items() if key in Step.__dataclass_fields__})
                for hint in hints
            ]
            logger.debug("Plan built from parser hints: %s steps", len(steps))
            return Plan(goal=goal, steps=steps)
        except (TypeError, KeyError) as exc:
            logger.warning("Failed to build plan from hints: %s", exc)

    context_str = build_plan_context(goal, state)
    raw = call_llm_cached("planner", PLANNER_SYSTEM, context_str, temperature=0.1)

    return _parse_plan(raw, goal, fallback_decision=decision)


def replan(original_plan: Plan, failed_step: Step, state, memory) -> Optional[Plan]:
    """
    Called by the executor when a step fails.
    Asks LLM to generate a recovery plan.
    Max 2 replans per plan to avoid loops.
    """
    if original_plan.replan_count >= 2:
        logger.warning("Max replan count reached - giving up")
        return None

    logger.info(
        "Replanning after step %s (%s) failed",
        failed_step.index,
        failed_step.skill_name,
    )

    recovery_prompt = (
        f"Original goal: {original_plan.goal}\n\n"
        f"Completed steps: {[step.description for step in original_plan.steps if step.success]}\n\n"
        f"Failed step: {failed_step.description}\n"
        f"Failure reason: {failed_step.error}\n\n"
        f"Current context: active_app={state.active_app or 'none'}\n\n"
        "Generate a recovery plan to achieve the original goal."
    )

    raw = call_llm_cached("replan", REPLAN_SYSTEM, recovery_prompt, temperature=0.2)
    recovery = _parse_plan(raw, original_plan.goal, fallback_decision=None)

    if recovery:
        recovery.replan_count = original_plan.replan_count + 1
        recovery.context = original_plan.context.copy()
        return recovery

    return None


def _parse_plan(raw: str, goal: str, fallback_decision: Optional[dict]) -> Plan:
    """Parse LLM JSON output into a Plan. Falls back to single-step plan on error."""
    try:
        raw_clean = str(raw or "").strip()
        if raw_clean.startswith("```"):
            raw_clean = raw_clean.split("```")[1]
            if raw_clean.startswith("json"):
                raw_clean = raw_clean[4:]
        data = json.loads(raw_clean.strip())
    except json.JSONDecodeError as exc:
        logger.error("Planner JSON parse error: %s. Raw: %s", exc, str(raw or "")[:200])
        return _fallback_plan(goal, fallback_decision)

    valid, reason = _validate_plan(data)
    if not valid:
        logger.error("Plan validation failed: %s", reason)
        return _fallback_plan(goal, fallback_decision)

    try:
        steps = [
            Step(
                index=step["index"],
                skill_name=step["skill_name"],
                description=step.get("description", ""),
                params=step.get("params", {}),
                depends_on=step.get("depends_on", []),
                output_key=step.get("output_key"),
            )
            for step in data["steps"]
        ]
        return Plan(goal=data.get("goal", goal), steps=steps)
    except (KeyError, TypeError) as exc:
        logger.error("Plan construction error: %s", exc)
        return _fallback_plan(goal, fallback_decision)


def _fallback_plan(goal: str, decision: Optional[dict]) -> Plan:
    """Single-step fallback plan using the original decision."""
    skill = "respond"
    params = {}
    if decision:
        skill = decision.get("name", "respond")
        params = decision.get("parameters", {})
    step = Step(index=0, skill_name=skill, description=goal, params=params)
    return Plan(goal=goal, steps=[step])


__all__ = ["Plan", "Step", "_needs_plan", "plan", "replan"]
