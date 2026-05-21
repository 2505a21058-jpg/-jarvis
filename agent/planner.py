"""
agent/planner.py

Adaptive DAG-based planner for Jarvis v2.
Features:
  - Conditional planning: only triggers for genuinely multi-step tasks
  - DAG-aware step definitions with dependency tracking
  - PlanGraph execution with per-step retry and timeout metadata
  - Replanning: when a step fails, LLM generates a recovery plan
  - Plan validation before execution
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from agent.context import build_plan_context
from agent.executor import ExecutionResult, get_executor
from models.llm import call_llm_cached


logger = logging.getLogger("jarvis.planner")


@dataclass
class PlanStep:
    """A single dependency-aware action in a DAG plan."""
    id: str
    skill: str
    params: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    retries: int = 1
    timeout: Optional[int] = None
    description: str = ""
    output_key: Optional[str] = None
    legacy_index: int = 0

    result: Optional[ExecutionResult] = None
    status: str = "pending"


@dataclass
class PlanGraph:
    """Small adjacency-list DAG wrapper for dependency-aware plan execution."""
    steps: dict[str, PlanStep] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)

    def add(self, step: PlanStep):
        self.steps[step.id] = step

    def topological_order(self) -> list[str]:
        """Return step ids in valid execution order using Kahn's algorithm."""
        in_degree = {sid: 0 for sid in self.steps}
        for step in self.steps.values():
            for dep in step.depends_on:
                if dep in in_degree:
                    in_degree[step.id] = in_degree.get(step.id, 0) + 1

        queue = [sid for sid, degree in in_degree.items() if degree == 0]
        order = []

        while queue:
            sid = queue.pop(0)
            order.append(sid)
            for step in self.steps.values():
                if sid in step.depends_on:
                    in_degree[step.id] -= 1
                    if in_degree[step.id] == 0:
                        queue.append(step.id)

        if len(order) != len(self.steps):
            logger.warning("Plan graph has cycles - falling back to insertion order")
            return list(self.steps.keys())

        return order

    def ready_steps(self) -> list[PlanStep]:
        """Return pending steps whose dependencies are done; future parallel runner hook."""
        ready = []
        for step in self.steps.values():
            if step.status != "pending":
                continue
            if all(
                self.steps[dep].status == "done"
                for dep in step.depends_on
                if dep in self.steps
            ):
                ready.append(step)
        return ready


def execute_plan(
    graph: PlanGraph,
    state=None,
    replan_hook: Optional[Callable[[PlanStep, ExecutionResult], Optional[PlanStep]]] = None,
) -> dict[str, ExecutionResult]:
    """
    Execute a PlanGraph in topological order.
    Failed steps can be substituted by replan_hook without changing executor.py.
    """
    executor = get_executor()
    results: dict[str, ExecutionResult] = {}

    for sid in graph.topological_order():
        step = graph.steps[sid]

        dep_failed = any(
            graph.steps[dep].status in {"failed", "skipped"}
            for dep in step.depends_on
            if dep in graph.steps
        )
        if dep_failed:
            step.status = "skipped"
            logger.info("[PLANNER] Skipping %s (dependency failed)", sid)
            results[sid] = ExecutionResult(
                success=False,
                output=None,
                error="Blocked by failed dependency",
                skill_name=step.skill,
                step_index=step.legacy_index,
            )
            continue

        step.status = "running"
        logger.info("[PLANNER] Executing step: %s (%s)", sid, step.skill)

        resolved_params = _resolve_step_params(step.params, graph.context)
        result = _execute_graph_step(executor, step, resolved_params, state)

        step.result = result
        results[sid] = result

        if result.success:
            step.status = "done"
            _record_step_output(graph.context, step, result.output)
            logger.info("[PLANNER] Step %s done (%.0fms)", sid, result.elapsed_ms)
            continue

        step.status = "failed"
        logger.warning("[PLANNER] Step %s failed: %s", sid, result.error)

        if not replan_hook:
            continue

        replacement = replan_hook(step, result)
        if not replacement:
            continue

        logger.info("[PLANNER] Replanning: replacing %s with %s", sid, replacement.id)
        graph.add(replacement)
        replacement.status = "running"
        replacement_params = _resolve_step_params(replacement.params, graph.context)
        rep_result = _execute_graph_step(executor, replacement, replacement_params, state)
        replacement.result = rep_result
        replacement.status = "done" if rep_result.success else "failed"
        if rep_result.success:
            step.status = "done"
            _record_step_output(graph.context, step, rep_result.output)
            _record_step_output(graph.context, replacement, rep_result.output)
        results[replacement.id] = rep_result

    return results


def _execute_graph_step(executor: Any, step: PlanStep, params: dict, state: Any) -> ExecutionResult:
    """Call the centralized executor while tolerating simple test doubles."""
    try:
        return executor.execute(
            step.skill,
            params,
            state,
            timeout=step.timeout,
            retries=step.retries,
            step_index=step.legacy_index,
        )
    except TypeError as exc:
        if "step_index" not in str(exc):
            raise
        result = executor.execute(
            step.skill,
            params,
            state,
            timeout=step.timeout,
            retries=step.retries,
        )
        if hasattr(result, "step_index"):
            result.step_index = step.legacy_index
        return result


def _resolve_step_params(params: dict, context: dict) -> dict:
    """Resolve {output_key} references using prior step outputs."""
    resolved = {}
    for key, value in (params or {}).items():
        if isinstance(value, str):
            try:
                resolved[key] = value.format(**context)
            except KeyError:
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


def _record_step_output(context: dict, step: PlanStep, output: Any) -> None:
    """Store successful outputs for later dependent params without changing skill APIs."""
    if step.output_key:
        context[step.output_key] = output
    context[f"step_{step.legacy_index}_result"] = output


def build_plan_from_steps(step_dicts: list[dict | "Step" | PlanStep]) -> PlanGraph:
    """
    Build a PlanGraph from LLM step dicts, legacy Step objects, or PlanStep objects.
    Supports both new ids and existing index/skill_name planner output.
    """
    graph = PlanGraph()
    index_to_id: dict[Any, str] = {}
    normalized: list[dict[str, Any]] = []

    for position, raw_step in enumerate(step_dicts or []):
        if isinstance(raw_step, PlanStep):
            graph.add(raw_step)
            continue

        if isinstance(raw_step, Step):
            data = {
                "id": f"step_{raw_step.index}",
                "index": raw_step.index,
                "skill": raw_step.skill_name,
                "params": raw_step.params,
                "depends_on": raw_step.depends_on,
                "description": raw_step.description,
            }
        else:
            data = dict(raw_step or {})

        sid = str(data.get("id") or f"step_{data.get('index', position)}")
        data["id"] = sid
        normalized.append(data)
        if "index" in data:
            index_to_id[data["index"]] = sid

    for data in normalized:
        deps = []
        for dep in data.get("depends_on", []) or []:
            deps.append(index_to_id.get(dep, str(dep)))

        step = PlanStep(
            id=str(data["id"]),
            skill=str(data.get("skill") or data.get("skill_name") or "respond"),
            params=dict(data.get("params", {}) or {}),
            depends_on=deps,
            retries=int(data.get("retries", 1) or 0),
            timeout=data.get("timeout"),
            description=str(data.get("description", "") or ""),
            output_key=data.get("output_key"),
            legacy_index=int(data.get("index", len(graph.steps)) or 0),
        )
        graph.add(step)

    return graph


@dataclass
class Step:
    index: int
    skill_name: str
    description: str
    params: dict = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)
    retries: int = 1
    timeout: Optional[int] = None
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


def _build_planner_system() -> str:
    """Dynamically build the planner system prompt from the app registry."""
    try:
        from skills.app_registry import get_app_registry
        registry = get_app_registry()
        playable = registry.playable_apps()
        searchable = registry.searchable_apps()
    except Exception:
        playable = ["youtube", "spotify", "soundcloud"]
        searchable = ["youtube", "google", "youtube music"]

    playable_str = ", ".join(playable)
    searchable_str = ", ".join(searchable)

    return f"""
You are a precise task planner for an AI assistant.
Decompose the given goal into a minimal sequence of steps.

Use ONLY these exact skill names (no others):
  open_app        - open a desktop app or web service by name
  browse          - navigate browser to a URL (params: url)
  type_text       - type text into active app (params: text)
  search          - web search (params: query)
  system_command  - run a system command
  system_search   - search local files/folders (params: query)
  open_and_search - open app then search (params: app, query)
  open_search_and_play - open app, search, then open/play first result (params: app, query)
  open_and_type   - open app then type text (params: app, text)
  compose_email   - compose and send email (params: to, body)
  reminder        - set a reminder (params: message, delay)
  web_summary     - search web and summarize a topic (params: topic)
  respond         - generate a text response or answer (params: query)
  run_code        - write and execute Python code for a task (params: task)
  gui_automate    - click UI elements or type into apps via accessibility API (params: action, element/app/text)
  computer_control - general app/browser/desktop automation for broad multi-step tasks (params: task)

Rules:
- Use the FEWEST steps possible
- Each step may include a stable id like "step_0" and must have a unique output_key (snake_case)
- depends_on lists step indices this step needs output from
- Maximum 5 steps
- If goal needs just a text answer, use ONE step with skill respond
- If goal is open app THEN type, use ONE step with skill open_and_type
- NEVER use skill names not in the list above

CRITICAL RULES TO PREVENT WRONG PLANS:
- For apps that support search+play ({playable_str}), use open_search_and_play with app="<app_name>"
- For other searchable apps ({searchable_str}), use open_and_search with app="<app_name>"
- NEVER open "notepad" unless the user explicitly asked for notepad
- NEVER open a different app than what the user mentioned
- If unsure about app name, use browse with the full URL instead
- For "open X and search Y", use open_and_search skill, not open_app + search separately
- For "play/watch first result", use open_search_and_play skill
- For broad device/app control requests, use computer_control with the full user task
- For app workflows that need UI state (clicking, filling forms, drawing, bookings), use ONE computer_control step
- Do not decompose desktop GUI workflows yourself; computer_control runs its own observe-act-verify recovery loop
- For bookings, payments, purchases, deletes, or submissions, stop for user confirmation before final action

Return ONLY valid JSON, no markdown, no explanation:
{{
  "goal": "string",
  "steps": [
    {{
      "id": "step_0",
      "index": 0,
      "skill_name": "open_app",
      "description": "string",
      "params": {{"app": "notepad"}},
      "depends_on": [],
      "output_key": "app_result"
    }}
  ]
}}
"""

REPLAN_SYSTEM = """
You are a recovery planner. A step in an AI task plan has failed.
Generate a revised plan that achieves the original goal while working around the failure.

Return ONLY valid JSON in the same format as the original plan.
Use ONLY these skill names: open_app, browse, type_text, search, system_command,
system_search, open_and_search, open_search_and_play, open_and_type, compose_email, reminder,
web_summary, respond, system_monitor, read_report, launch_claude_code, computer_control,
send_email, list_skills, open_and_browse, run_code, gui_automate

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

    valid_skills = {
        "open_app", "browse", "type_text", "search",
        "system_command", "system_search", "open_and_search", "open_search_and_play", "open_and_type",
        "compose_email", "reminder", "web_summary", "respond",
        "system_monitor", "read_report", "launch_claude_code", "computer_control",
        "send_email", "list_skills", "open_and_browse",
        "run_code", "gui_automate",
    }

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
    raw = call_llm_cached("planner", _build_planner_system(), context_str, temperature=0.1, max_tokens=700)

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

    raw = call_llm_cached("replan", REPLAN_SYSTEM, recovery_prompt, temperature=0.2, max_tokens=700)
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
                retries=step.get("retries", 1),
                timeout=step.get("timeout"),
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


__all__ = [
    "Plan",
    "Step",
    "PlanStep",
    "PlanGraph",
    "build_plan_from_steps",
    "execute_plan",
    "_needs_plan",
    "plan",
    "replan",
]
