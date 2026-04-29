from __future__ import annotations

import logging
from typing import Any, Callable

from agent.executor import Executor, get_executor
from agent.planner import Plan
from agent.response_cleaner import clean_response
from agent.state import State
from model_manager import FAST_MODEL, NERD_MODEL, SMART_MODEL
from models.llm import JARVIS_CORE_MODEL, run_llm
from skills.registry import SkillRegistry


MAX_RETRIES = 2
FAILURE_PREFIXES = (
    "failed",
    "error",
    "i dont know how to open",
    "i don't know how to open",
    "nothing to type",
    "no active app",
    "could not",
    "please provide",
)
logger = logging.getLogger("jarvis.agent.act")


def _extract_parameters(decision: dict[str, Any]) -> dict[str, Any]:
    parameters = decision.get("parameters", {})
    if isinstance(parameters, dict):
        return dict(parameters)
    return {}


def _get_request_text(decision: dict[str, Any], parameters: dict[str, Any]) -> str:
    for key in ("input", "query", "prompt", "text", "observation_input"):
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("query", "target", "text", "app_name", "source", "value"):
        value = parameters.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    name = str(decision.get("name", "")).strip()
    return name


def _is_failure_output(output: Any) -> bool:
    if output is None:
        return True

    if isinstance(output, dict) and "success" in output:
        return not bool(output.get("success"))

    text = str(output).strip().lower()
    if not text:
        return True

    return text.startswith(FAILURE_PREFIXES)


def _make_result(
    success: bool,
    output: Any = None,
    error: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "output": output,
        "error": error,
        "steps": steps or [],
    }


def _clean_result_output(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("output"), str):
        cleaned = clean_response(result["output"], decision)
        if cleaned != result["output"]:
            result = dict(result)
            result["output"] = cleaned
    return result


def _normalize_handler_output(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict) and {"success", "output", "error"} <= set(raw_output.keys()):
        return _make_result(
            bool(raw_output.get("success")),
            raw_output.get("output"),
            raw_output.get("error"),
            list(raw_output.get("steps") or []),
        )

    if _is_failure_output(raw_output):
        error_text = str(raw_output).strip() or "Execution failed."
        return _make_result(False, raw_output, error_text)

    return _make_result(True, raw_output, None)


def _skill_weather(parameters: dict[str, Any]) -> Any:
    from skills.weather import get_weather

    city = str(parameters.get("city") or parameters.get("target") or "Hyderabad").strip()
    return get_weather(city or "Hyderabad")


def _skill_time(parameters: dict[str, Any]) -> Any:
    from skills.datetime_skill import get_datetime

    return get_datetime()


def _skill_pnr(parameters: dict[str, Any]) -> Any:
    from skills.train import check_pnr

    pnr = str(parameters.get("pnr") or parameters.get("target") or "").strip()
    if not pnr:
        return "Please provide a valid PNR."
    return check_pnr(pnr)


def _skill_train(parameters: dict[str, Any]) -> Any:
    from skills.train import get_live_train

    train_number = str(parameters.get("train_number") or parameters.get("target") or "").strip()
    if not train_number:
        return "Please provide a valid train number."
    return get_live_train(train_number)


SKILL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "weather": _skill_weather,
    "time": _skill_time,
    "date": _skill_time,
    "pnr": _skill_pnr,
    "train": _skill_train,
}


MODE_MODEL_MAP = {
    "fast": FAST_MODEL,
    "smart": SMART_MODEL,
    "nerd": NERD_MODEL,
}
MODE_OPTIONS_MAP = {
    "fast": {"temperature": 0.7, "num_predict": 220},
    "smart": {"temperature": 0.5, "num_predict": 700},
    "nerd": {"temperature": 0.3, "num_predict": 1200},
}
AUTOMATION_SKILL_MAP = {
    "open": "open_app",
    "open_app": "open_app",
    "search": "browse",
    "search_web": "browse",
    "browse": "browse",
    "play": "browse",
    "play_music": "browse",
    "type": "type_text",
    "type_text": "type_text",
}
PLAN_SKILL_MAP = {
    "open": "open_app",
    "open_app": "open_app",
    "search": "browse",
    "search_web": "browse",
    "find": "browse",
    "watch": "browse",
    "browse": "browse",
    "play": "browse",
    "play_music": "browse",
    "type": "type_text",
    "type_text": "type_text",
    "llm": "__respond__",
    "respond": "__respond__",
    "system_command": "__unsupported__",
}


def _mode_name(decision: dict[str, Any]) -> str:
    mode = str(decision.get("mode", "fast")).strip().lower()
    return mode if mode in MODE_MODEL_MAP else "fast"


def _mode_system_prompt(mode: str) -> str:
    base = (
        "You are Jarvis, a personal AI assistant created by the user.\n"
        "Stay calm, practical, and clear.\n"
        "Start with a direct answer.\n"
        "Then explain the reasoning.\n"
        "Use memory and recent history only when they help the answer.\n"
        "Do not pretend a tool succeeded if it failed."
    )

    if mode == "fast":
        return base + "\nKeep the response concise and useful."
    if mode == "smart":
        return base + "\nBalance clarity, reasoning, and tradeoffs."
    return base + "\nGo deeper on analysis, risks, opportunities, and strategy."


def _format_memory_context(memory_payload: Any) -> str:
    if not isinstance(memory_payload, dict):
        return ""

    parts = []
    profile = memory_payload.get("profile")
    matches = memory_payload.get("matches")
    recent = memory_payload.get("recent")

    if profile:
        parts.append(f"Memory profile: {profile}")
    if matches:
        parts.append(f"Relevant memory: {matches}")
    if recent:
        parts.append(f"Recent memory: {recent}")

    return "\n".join(parts)


def _format_recent_history(recent_history: Any) -> str:
    if not isinstance(recent_history, list) or not recent_history:
        return ""
    return f"Recent state history: {recent_history}"


def _state_context(decision: dict[str, Any]) -> dict[str, Any]:
    state_obj = decision.get("_state_obj")
    if hasattr(state_obj, "to_context_dict"):
        return state_obj.to_context_dict()

    state_payload = decision.get("state")
    if isinstance(state_payload, dict):
        return {
            "mode": state_payload.get("mode"),
            "active_app": state_payload.get("active_app"),
            "active_platform": state_payload.get("active_platform"),
            "search_engine": state_payload.get("search_engine"),
            "browser_url": state_payload.get("browser_url"),
            "task_stack_depth": len(state_payload.get("task_stack", []) or []),
        }
    return {}


def _llm_messages(decision: dict[str, Any], request_text: str, error_context: str | None) -> list[dict[str, Any]]:
    mode = _mode_name(decision)
    system_prompt = _mode_system_prompt(mode)
    state_context = _state_context(decision)
    context_parts = [
        f"State context: {state_context}" if state_context else "",
        _format_memory_context(decision.get("memory")),
        _format_recent_history(decision.get("recent_history")),
    ]
    context_block = "\n".join(part for part in context_parts if part)

    user_parts = []
    if context_block:
        user_parts.append(context_block)
    user_parts.append(f"User request: {request_text or 'Help with the user request.'}")
    if error_context:
        user_parts.append(f"Tool or skill failure: {error_context}")

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def _run_llm_action(decision: dict[str, Any], *, error_context: str | None = None) -> dict[str, Any]:
    parameters = _extract_parameters(decision)
    request_text = _get_request_text(decision, parameters)
    failure_ctx = parameters.get("_failure_context")
    failure_note = ""
    if failure_ctx:
        failure_note = (
            f"\n[SYSTEM NOTE: Previous attempt failed with type='{failure_ctx}'. "
            "Try a different approach.]"
        )
    request_text = f"{request_text or 'Help with the user request.'}{failure_note}"
    mode = _mode_name(decision)
    model_name = str(decision.get("model") or MODE_MODEL_MAP.get(mode) or JARVIS_CORE_MODEL)
    options = dict(MODE_OPTIONS_MAP.get(mode, MODE_OPTIONS_MAP["fast"]))
    if isinstance(decision.get("options"), dict):
        options.update(decision["options"])

    response = run_llm(
        _llm_messages(decision, request_text, error_context),
        model=model_name,
        options=options,
    )
    content = str(response.get("message", {}).get("content", "")).strip()
    if not content:
        return _make_result(False, None, "LLM returned empty output.")
    return _make_result(True, clean_response(content, decision), None)


def _execute_handler(
    label: str,
    handler: Callable[[dict[str, Any]], Any],
    parameters: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    last_error = "Execution failed."

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_output = handler(parameters)
            normalized = _normalize_handler_output(raw_output)
            steps.append(
                {
                    "attempt": attempt,
                    "action": label,
                    "success": normalized["success"],
                    "error": normalized["error"],
                }
            )
            if normalized["success"]:
                normalized["steps"] = steps
                return normalized
            last_error = normalized["error"] or last_error
        except Exception as exc:
            last_error = str(exc)
            steps.append(
                {
                    "attempt": attempt,
                    "action": label,
                    "success": False,
                    "error": last_error,
                }
            )

    return _make_result(False, None, last_error, steps)


def _coerce_state_object(state_value: Any) -> State:
    if isinstance(state_value, State):
        return state_value

    if isinstance(state_value, dict):
        field_names = set(State.__dataclass_fields__)
        filtered = {key: value for key, value in state_value.items() if key in field_names}
        return State(**filtered)

    return State()


def _registry_request(decision_name: str, parameters: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    skill_name = AUTOMATION_SKILL_MAP.get(decision_name)
    if not skill_name:
        registry = SkillRegistry.instance()
        if registry.get(decision_name):
            return decision_name, parameters
        return None, parameters

    if skill_name == "open_app":
        target = str(parameters.get("app") or parameters.get("target") or parameters.get("app_name") or parameters.get("name") or "").strip()
        url = str(parameters.get("url") or "").strip()
        payload = {"app": target}
        if url:
            payload["url"] = url
        return skill_name, payload

    if decision_name in {"play", "play_music"}:
        source = str(parameters.get("source") or parameters.get("target") or "").strip()
        query = "!sp" if not source else f"!sp {source}"
        return skill_name, {"query": query}

    if skill_name == "browse":
        url = str(parameters.get("url") or "").strip()
        query = str(parameters.get("query") or parameters.get("target") or "").strip()
        if url:
            return skill_name, {"url": url}
        return skill_name, {"query": query}

    if skill_name == "type_text":
        text = str(parameters.get("text") or parameters.get("target") or "").strip()
        return skill_name, {"text": text}

    return skill_name, parameters


def _execute_registry_skill(
    decision_name: str,
    parameters: dict[str, Any],
    state: State,
    steps: list[dict[str, Any]],
) -> dict[str, Any] | None:
    skill_name, skill_params = _registry_request(decision_name, parameters)
    if not skill_name:
        return None

    executor: Executor = get_executor()
    exec_result = executor.execute(
        skill_name=skill_name,
        params=skill_params,
        state=state,
        step_index=0,
    )
    logger.info(
        "skill=%s attempts=%s duration_ms=%.2f verified=%s error=%s",
        skill_name,
        exec_result.attempts,
        exec_result.duration_ms,
        exec_result.verified,
        exec_result.error,
    )
    steps.append(
        {
            "attempt": exec_result.attempts,
            "action": f"skill:{skill_name}",
            "success": exec_result.success,
            "error": exec_result.error,
            "duration_ms": round(exec_result.duration_ms, 2),
            "verified": exec_result.verified,
        }
    )
    if exec_result.success:
        return _make_result(True, exec_result.output, None, steps)

    logger.error(
        "Skill execution failed after %s attempts: %s",
        exec_result.attempts,
        exec_result.error,
    )
    return _make_result(False, None, exec_result.error or f"Unknown skill: {skill_name}", steps)


def _resolve_handler(decision_type: str, decision_name: str):
    if decision_type == "skill":
        return SKILL_HANDLERS.get(decision_name)
    return None


def _resolve_params(params: dict, context: dict) -> dict:
    """Replace {key} templates in param values with values from context."""
    resolved = {}
    for key, value in (params or {}).items():
        if isinstance(value, str):
            try:
                resolved[key] = value.format(**(context or {}))
            except KeyError:
                resolved[key] = value
        else:
            resolved[key] = value
    return resolved


def _plan_registry_request(skill_name: str, params: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    normalized_name = PLAN_SKILL_MAP.get(str(skill_name or "").strip().lower(), str(skill_name or "").strip().lower())
    payload = dict(params or {})

    if normalized_name == "__respond__":
        return normalized_name, payload
    if normalized_name == "__unsupported__":
        return normalized_name, payload

    if normalized_name == "open_app":
        target = str(
            payload.get("app")
            or payload.get("target")
            or payload.get("app_name")
            or payload.get("name")
            or ""
        ).strip()
        return normalized_name, {"app": target, **({"url": str(payload.get("url")).strip()} if payload.get("url") else {})}

    if normalized_name == "browse":
        url = str(payload.get("url") or "").strip()
        query = str(payload.get("query") or payload.get("target") or payload.get("text") or "").strip()
        if url:
            return normalized_name, {"url": url}
        return normalized_name, {"query": query}

    if normalized_name == "type_text":
        text = str(payload.get("text") or payload.get("target") or "").strip()
        return normalized_name, {"text": text}

    registry = SkillRegistry.instance()
    if registry.get(normalized_name):
        return normalized_name, payload

    return None, payload


def _execute_plan(plan_obj: Plan, state: State, memory: Any) -> dict[str, Any]:
    """
    Execute a Plan through the executor layer with replanning.
    """
    from agent.planner import replan

    executor = get_executor()
    while True:
        results, context = executor.execute_plan(plan_obj.steps, state)
        merged_context = dict(plan_obj.context)
        merged_context.update(context)
        plan_obj.context = merged_context

        failed = [result for result in results if not result.success]
        succeeded = [result for result in results if result.success]

        for step in plan_obj.steps:
            matching = next((result for result in results if result.step_index == step.index), None)
            if matching is None:
                continue
            step.result = matching.output
            step.success = matching.success
            step.error = matching.error

        if not failed:
            plan_obj.completed = True
            plan_obj.failed = False
            plan_obj.failure_reason = None
            if hasattr(state, "record_plan_execution"):
                state.record_plan_execution(plan_obj)
            outputs = [str(result.output) for result in succeeded if result.output]
            return _clean_result_output(_make_result(
                True,
                "\n".join(outputs) if outputs else "Plan completed successfully.",
                None,
                [
                    {
                        "step": result.step_index,
                        "skill_name": result.skill_name,
                        "success": result.success,
                        "error": result.error,
                        "attempts": result.attempts,
                        "duration_ms": round(result.duration_ms, 2),
                        "verified": result.verified,
                    }
                    for result in results
                ],
            ), dict(plan_obj.context.get("_decision", {})))

        first_failure = failed[0]
        failed_step = next(
            (step for step in plan_obj.steps if step.index == first_failure.step_index),
            None,
        )

        if failed_step:
            failed_step.error = first_failure.error
            recovery_plan = replan(plan_obj, failed_step, state, memory)
            if recovery_plan:
                logger.info("Replanning successful - executing recovery plan")
                plan_obj = recovery_plan
                continue

        plan_obj.failed = True
        plan_obj.completed = False
        plan_obj.failure_reason = "; ".join(
            f"Step {result.step_index} ({result.skill_name}): {result.error}" for result in failed
        )
        if hasattr(state, "record_plan_execution"):
            state.record_plan_execution(plan_obj)
        outputs = [str(result.output) for result in succeeded if result.output]
        result_text = "\n".join(outputs) if outputs else ""
        final_output = f"{result_text}\nPartially failed: {plan_obj.failure_reason}".strip()
        return _clean_result_output(_make_result(
            False,
            final_output,
            plan_obj.failure_reason,
            [
                {
                    "step": result.step_index,
                    "skill_name": result.skill_name,
                    "success": result.success,
                    "error": result.error,
                    "attempts": result.attempts,
                    "duration_ms": round(result.duration_ms, 2),
                    "verified": result.verified,
                }
                for result in results
            ],
        ), dict(plan_obj.context.get("_decision", {})))


def _act_single_decision(decision: dict[str, Any], steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    decision = dict(decision or {})
    execution_steps = steps if steps is not None else []
    if decision.get("type") == "fast_chat" and "direct_response" in decision:
        return _clean_result_output(_make_result(
            True,
            str(decision.get("direct_response", "")).strip(),
            None,
            execution_steps + [
                {"attempt": 1, "action": "fast_chat", "success": True, "error": None}
            ],
        ), decision)

    decision_type = str(decision.get("type", "")).strip().lower()
    decision_name = str(decision.get("name", "")).strip().lower()
    parameters = _extract_parameters(decision)
    state = _coerce_state_object(decision.get("_state_obj") or decision.get("state"))
    memory = decision.get("_memory_obj")

    if decision_type == "teach_skill":
        from agent.skill_teacher import teach_skill

        if memory is None:
            return _make_result(False, None, "Memory is required to teach a skill.", execution_steps)

        message = teach_skill(str(parameters.get("raw_input") or ""), memory)
        return _make_result(True, message, None, execution_steps + [
            {"attempt": 1, "action": "teach_skill", "success": True, "error": None}
        ])

    if decision_type == "llm":
        llm_result = _run_llm_action(decision)
        llm_result["steps"] = execution_steps + [
            {"attempt": 1, "action": "llm", "success": llm_result["success"], "error": llm_result["error"]}
        ]
        return llm_result

    registry_result = None
    if decision_type in {"tool", "skill"}:
        registry_result = _execute_registry_skill(decision_name, parameters, state, execution_steps)

    if registry_result is not None:
        if registry_result["success"]:
            return _clean_result_output(registry_result, decision)

        fallback_result = _run_llm_action({**decision, "state": state.to_dict()}, error_context=registry_result["error"])
        fallback_result["steps"] = execution_steps + [
            {
                "attempt": 1,
                "action": "llm_fallback",
                "success": fallback_result["success"],
                "error": registry_result["error"],
            }
        ]
        return _clean_result_output(fallback_result, decision)

    handler = _resolve_handler(decision_type, decision_name)

    if handler is None:
        error_text = f"Unsupported decision target: {decision_type}:{decision_name}"
        fallback_result = _run_llm_action(decision, error_context=error_text)
        fallback_result["steps"] = execution_steps + [
            {"attempt": 1, "action": "llm_fallback", "success": fallback_result["success"], "error": error_text}
        ]
        return _clean_result_output(fallback_result, decision)

    result = _execute_handler(f"{decision_type}:{decision_name}", handler, parameters, execution_steps)
    if result["success"]:
        return _clean_result_output(result, decision)

    fallback_result = _run_llm_action(decision, error_context=result["error"])
    fallback_result["steps"] = execution_steps + [
        {
            "attempt": 1,
            "action": "llm_fallback",
            "success": fallback_result["success"],
            "error": result["error"],
        }
    ]
    return _clean_result_output(fallback_result, decision)


def act(
    decision: dict[str, Any],
    memory: Any = None,
    state: State | None = None,
    plan: Plan | None = None,
) -> dict[str, Any]:
    decision = dict(decision or {})
    execution_state = state or _coerce_state_object(decision.get("_state_obj") or decision.get("state"))

    if state is not None:
        decision["_state_obj"] = state
        decision["state"] = state.to_dict()
    if memory is not None:
        decision["_memory_obj"] = memory

    if plan is not None:
        plan.context.setdefault("_decision", dict(decision))
        return _clean_result_output(_execute_plan(plan, execution_state, memory), decision)

    return _clean_result_output(_act_single_decision(decision), decision)
