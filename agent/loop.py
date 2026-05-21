from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from agent.evaluate import EvaluationResult, evaluate
from agent.intent.classifier import classify
from agent.intent.router import route
from agent.intent.schema import Intent, IntentName
from agent.learn import learn
from agent.response_cleaner import clean_response
from agent.state import State, update_state
from memory.core import Memory
from models.model_router import get_model_for_intent


EXIT_COMMANDS = {"quit", "exit", "bye"}
logger = logging.getLogger("jarvis.agent.loop")


def _build_trace(
    observation: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    execution_plan: list[dict[str, Any]] | None,
    result: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "input": (observation or {}).get("input", ""),
        "observation": observation or {},
        "decision": decision or {},
        "plan": execution_plan or [],
        "result": result or {},
        "evaluation": evaluation or {},
        "error": error,
    }


def _print_trace(cycle: int, trace: dict[str, Any]):
    logger.debug("[Agent] Cycle %s", cycle)
    logger.debug(json.dumps(trace, indent=2, ensure_ascii=True, default=str))


def _evaluation_payload(evaluation: EvaluationResult) -> dict[str, Any]:
    return evaluation.to_dict()


def _post_cycle(
    user_input: str,
    result: dict[str, Any],
    decision: dict[str, Any],
    memory: Memory,
    state: State,
    *,
    source: str,
    observation: dict[str, Any] | None = None,
    execution_plan: list[dict[str, Any]] | None = None,
    evaluation_result: EvaluationResult | None = None,
    allow_retry: bool = False,
    emit_trace: bool = False,
    cycle: int = 1,
    exec_success: Optional[bool] = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], State]:
    result = dict(result or {})
    if isinstance(result.get("output"), str):
        result["output"] = clean_response(result["output"], decision)

    response_text = str(result.get("output") or "")
    intent_name = str(decision.get("intent") or decision.get("name") or "")
    evaluation_obj = evaluation_result or evaluate(
        output=response_text,
        original_input=user_input,
        intent_name=intent_name,
        use_llm=(source == "intent_llm" and intent_name in {"chat", "respond", "plan", "planner"} and len(response_text) > 50),
        exec_success=exec_success,
    )
    evaluation = _evaluation_payload(evaluation_obj)
    if evaluation_obj.retry_recommended and allow_retry:
        logger.warning(
            "[LOOP] Low confidence response (score=%.2f), retry recommended but not implemented yet",
            evaluation_obj.confidence,
        )
    learn(observation or {"input": user_input}, decision, result, evaluation, memory=memory)
    clean = clean_response(str(result.get("output") or ""), decision)
    state.add_to_conversation(role="user", content=user_input)
    state.add_to_conversation(role="assistant", content=clean)
    state.ui_context["last_response"] = clean
    state.ui_context["last_eval_confidence"] = evaluation_obj.confidence
    update_state(state, result, evaluation)

    if clean.strip():
        memory.store(
            {
                "user": str(user_input).strip(),
                "jarvis": clean.strip(),
                "timestamp": datetime.now().isoformat(),
                "mode": state.mode,
            }
        )

    trace = _build_trace(observation, decision, execution_plan or [], result, evaluation)
    if emit_trace:
        _print_trace(cycle, trace)
    logger.debug("Cycle complete [source=%s]", source)
    return result, evaluation, trace, state


def _make_result(
    success: bool,
    output: Any = None,
    error: str | None = None,
    action: str = "intent",
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "output": output,
        "error": error,
        "steps": [{"attempt": 1, "action": action, "success": bool(success), "error": error}],
    }


def _diagnostics_output(memory: Memory) -> str:
    from agent.executor import get_executor
    from agent.intent.classifier import get_stats as intent_stats
    from memory.core import get_stats as mem_stats

    istats = intent_stats()
    estats = get_executor().get_stats()
    mstats = mem_stats(memory)

    lines = [
        "-- Jarvis Diagnostics --",
        (
            f"Intent: {istats['total']} total | "
            f"rule={istats['rule_hit_rate']:.0%} | "
            f"llm={istats['llm_hit_rate']:.0%}"
        ),
        f"Executor: {sum(s['calls'] for s in estats.values())} skill calls",
        (
            "Memory: "
            f"{mstats['total']} total | recent={mstats['recent']} | "
            f"long_term={mstats['long_term']} | experience={mstats['experience']} | "
            f"profile={mstats['profile']} | semantic={mstats['semantic_available']}"
        ),
    ]

    for skill, stats in sorted(estats.items()):
        calls = int(stats.get("calls", 0) or 0)
        if calls <= 0:
            continue
        failures = int(stats.get("failures", 0) or 0)
        total_ms = float(stats.get("total_ms", 0.0) or 0.0)
        fail_rate = failures / max(calls, 1)
        avg_ms = total_ms / max(calls - failures, 1)
        lines.append(f"  {skill:<28} calls={calls} fail={fail_rate:.0%} avg={avg_ms:.0f}ms")

    return "\n".join(lines)


async def _execute_gemma_automation_plan(
    user_input: str,
    state: State,
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    from agent.executor import get_executor
    from skills.automation.gemma_bridge import plan_automation

    steps = plan_automation(user_input)
    if not steps:
        return None

    executor = get_executor()
    execution_plan: list[dict[str, Any]] = []
    result_steps: list[dict[str, Any]] = []
    last_output = ""
    first_error = ""
    success = True

    for index, step in enumerate(steps, start=1):
        skill_name = str(step.get("skill") or "").strip()
        params = step.get("params") if isinstance(step.get("params"), dict) else {}
        execution_plan.append({"index": index, "skill": skill_name, "params": params})

        if not skill_name:
            success = False
            first_error = "Gemma returned an automation step without a skill name"
            result_steps.append(
                {
                    "attempt": index,
                    "action": "gemma_plan:invalid",
                    "success": False,
                    "error": first_error,
                }
            )
            break

        exec_result = await executor.execute_async(skill_name, params, state, step_index=index)
        if exec_result.output:
            last_output = str(exec_result.output)
        if not exec_result.success and not first_error:
            first_error = exec_result.error or f"Automation step failed: {skill_name}"
        success = success and exec_result.success
        result_steps.append(
            {
                "attempt": index,
                "action": f"gemma_plan:{skill_name}",
                "success": bool(exec_result.success),
                "error": exec_result.error or None,
                "attempts": exec_result.attempts,
                "duration_ms": round(exec_result.duration_ms, 2),
                "verified": exec_result.verified,
            }
        )
        if not exec_result.success:
            break

    if success:
        output = last_output or f"Completed {len(result_steps)} automation step(s)."
    else:
        output = f"I couldn't complete that: {first_error or 'automation plan failed'}"

    result = _make_result(success, output, first_error or None, action="intent_gemma_plan")
    result["steps"] = result_steps
    return result, execution_plan


def _intent_decision(intent: Intent, skill_name: str = "") -> dict[str, Any]:
    return {
        "type": "intent",
        "name": skill_name or intent.name.value,
        "intent": intent.name.value,
        "confidence": intent.confidence,
        "requires_plan": False,
        "classification_source": intent.classification_source,
    }


def _intent_observation(user_input: str, intent: Intent, skill_name: str = "", params: dict | None = None) -> dict[str, Any]:
    return {
        "input": user_input,
        "intent": {
            "name": intent.name.value,
            "source": intent.classification_source,
            "confidence": intent.confidence,
            "entities": intent.to_skill_params(),
            "skill_name": skill_name,
            "params": params or {},
        },
    }


def _handle_set_config(intent: Intent) -> str:
    from jconfig import save_runtime_setting, get_config

    var = intent.get("var", "").upper()
    val = intent.get("val", "true")

    KNOWN_VARS = {
        "JARVIS_VISION_VERIFY": "Screenshot verification",
        "JARVIS_REMOTE_BRIDGE": "Remote control bridge",
        "JARVIS_HEARTBEAT": "Proactive monitoring",
        "JARVIS_MODEL": "Language model",
        "JARVIS_EMBED_MODEL": "Embedding model",
    }

    if not var or var not in KNOWN_VARS:
        known = ", ".join(KNOWN_VARS.keys())
        return f"Unknown setting '{var}'. Known settings: {known}"

    save_runtime_setting(var, val)
    get_config()
    desc = KNOWN_VARS[var]
    return (
        f"Set {var}={val} — saved to jconfig.yaml\n"
        f"Purpose: {desc}\n"
        "This setting will persist across restarts."
    )


def _chat_response(user_input: str, memory: Memory, state: State) -> str:
    memory_entries = memory.retrieve(user_input, mode="fast", limit=5)
    from agent.context import build_act_context
    from models.llm import call_llm

    context_str = build_act_context(
        user_input,
        memory_entries,
        state,
        {"type": "chat", "name": "respond"},
    )
    return call_llm(
        system=(
            "You are Jarvis, a helpful local AI assistant. "
            "Answer conversationally and accurately. "
            "Never hallucinate system stats or capabilities."
        ),
        user=context_str,
    )


async def run_agent_cycle(
    user_input: str,
    memory: Memory,
    state: State,
    *,
    emit_trace: bool = False,
    cycle: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], State]:
    intent: Intent | None = None
    decision: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None

    try:
        stripped = user_input.strip().lower()
        if stripped in ("/stats", "stats", "jarvis stats"):
            decision = {
                "type": "diagnostics",
                "name": "__diagnostics__",
                "confidence": 1.0,
                "requires_plan": False,
            }
            observation = {"input": user_input, "diagnostics": {"command": stripped}}
            return _post_cycle(
                user_input,
                _make_result(True, _diagnostics_output(memory), action="diagnostics:stats"),
                decision,
                memory,
                state,
                source="diagnostics",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        try:
            from memory.personal_facts import store_fact

            stored_fact = store_fact(user_input)
            if stored_fact:
                logger.info("Personal fact detected and stored: %s", stored_fact)
        except Exception as exc:
            logger.debug("Personal fact pre-store skipped: %s", exc)

        intent = classify(user_input)

        if intent.has("__learned_skill__"):
            from agent.executor import get_executor

            learned_skill_name = intent.get("__learned_skill__")
            logger.info("[LOOP] Executing learned skill directly: %s", learned_skill_name)
            exec_result = await get_executor().execute_async(learned_skill_name, {}, state)
            response = (
                str(exec_result.output)
                if exec_result.success
                else f"Learned skill failed: {exec_result.error}"
            )
            decision = _intent_decision(intent, learned_skill_name)
            observation = _intent_observation(user_input, intent, learned_skill_name)
            result = _make_result(
                exec_result.success,
                response,
                None if exec_result.success else exec_result.error,
                action=f"learned_rule:{learned_skill_name}",
            )
            result["steps"][0].update(
                {
                    "attempts": exec_result.attempts,
                    "duration_ms": round(exec_result.duration_ms, 2),
                    "verified": exec_result.verified,
                }
            )
            return _post_cycle(
                user_input,
                result,
                decision,
                memory,
                state,
                source="learned_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if intent.name == IntentName.GREETING:
            response = intent.get("response", "Hello! How can I help you today?")
            decision = _intent_decision(intent, "__direct_response__")
            observation = _intent_observation(user_input, intent, "__direct_response__")
            return _post_cycle(
                user_input,
                _make_result(True, response, action="intent:greeting"),
                decision,
                memory,
                state,
                source="intent_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if intent.name in (IntentName.ACKNOWLEDGEMENT, IntentName.FAREWELL):
            response = intent.get("response", "Got it.")
            decision = _intent_decision(intent, "__direct_response__")
            observation = _intent_observation(user_input, intent, "__direct_response__")
            return _post_cycle(
                user_input,
                _make_result(True, response, action=f"intent:{intent.name.value}"),
                decision,
                memory,
                state,
                source="intent_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if intent.name == IntentName.SET_CONFIG:
            response = _handle_set_config(intent)
            decision = _intent_decision(intent, "__set_env__")
            observation = _intent_observation(user_input, intent, "__set_env__")
            return _post_cycle(
                user_input,
                _make_result(True, response, action="intent:set_config"),
                decision,
                memory,
                state,
                source="intent_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if intent.name == IntentName.LEARN_SKILL:
            from agent.skill_teacher import teach_skill

            response = teach_skill(user_input, memory)
            decision = _intent_decision(intent, "__teach_skill__")
            observation = _intent_observation(user_input, intent, "__teach_skill__")
            return _post_cycle(
                user_input,
                _make_result(True, response, action="intent:learn_skill"),
                decision,
                memory,
                state,
                source="intent_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        skill_name, skill_params = route(intent)
        decision = _intent_decision(intent, skill_name)
        model = get_model_for_intent(intent.name)
        decision["model"] = model
        observation = _intent_observation(user_input, intent, skill_name, skill_params)

        if skill_name == "__direct_response__":
            response = intent.get("response", "")
            return _post_cycle(
                user_input,
                _make_result(True, response, action="intent:direct_response"),
                decision,
                memory,
                state,
                source="intent_rule",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if skill_name == "respond":
            if model == "gemma":
                from models.gemma import call_gemma

                response = call_gemma(
                    prompt=user_input,
                    system=(
                        "You are a computer automation assistant for Jarvis. "
                        "The user wants to control their PC. "
                        "Describe the exact steps to execute this action concisely."
                    ),
                )
            else:
                response = _chat_response(user_input, memory, state)
            return _post_cycle(
                user_input,
                _make_result(True, response, action="intent:respond"),
                decision,
                memory,
                state,
                source="intent_llm",
                observation=observation,
                emit_trace=emit_trace,
                cycle=cycle,
            )

        if model == "gemma":
            planned = await _execute_gemma_automation_plan(user_input, state)
            if planned is not None:
                result, execution_plan = planned
                return _post_cycle(
                    user_input,
                    result,
                    decision,
                    memory,
                    state,
                    source="intent_gemma",
                    observation=observation,
                    execution_plan=execution_plan,
                    emit_trace=emit_trace,
                    cycle=cycle,
                )

        if intent.name == IntentName.COMPUTER_USE:
            from agent.computer_use import ComputerUseAgent

            task = skill_params.get("task") or skill_params.get("goal") or user_input
            try:
                cu_result = ComputerUseAgent().run(task)
                success = cu_result.success
                response = cu_result.final_reason
                output = response if success else f"I couldn't complete that: {response}"
                result = _make_result(success, output, None if success else response, action="intent:computer_use")
                return _post_cycle(
                    user_input,
                    result,
                    decision,
                    memory,
                    state,
                    source="intent_skill",
                    observation=observation,
                    emit_trace=emit_trace,
                    cycle=cycle,
                    exec_success=success,
                )
            except Exception as exc:
                logger.exception("[COMPUTER USE] Agent failed: %s", exc)
                result = _make_result(False, f"Computer use failed: {exc}", str(exc), action="intent:computer_use")

        from agent.executor import get_executor

        exec_result = await get_executor().execute_async(skill_name, skill_params, state)
        if exec_result.success:
            response = str(exec_result.output) if exec_result.output else f"Completed {skill_name}."
            result = _make_result(True, response, action=f"intent_skill:{skill_name}")
            result["steps"][0].update(
                {
                    "attempts": exec_result.attempts,
                    "duration_ms": round(exec_result.duration_ms, 2),
                    "verified": exec_result.verified,
                }
            )
        else:
            response = f"I couldn't complete that: {exec_result.error}"
            result = _make_result(False, response, exec_result.error, action=f"intent_skill:{skill_name}")
            result["steps"][0].update(
                {
                    "attempts": exec_result.attempts,
                    "duration_ms": round(exec_result.duration_ms, 2),
                    "verified": exec_result.verified,
                }
            )

        return _post_cycle(
            user_input,
            result,
            decision,
            memory,
            state,
            source="intent_skill",
            observation=observation,
            emit_trace=emit_trace,
            cycle=cycle,
            exec_success=exec_result.success,
        )

    except RuntimeError as exc:
        logger.error("Agent cycle LLM failure: %s", exc)
        result = _make_result(False, "I encountered a model error. Please try again.", str(exc), "intent:error")
    except TimeoutError as exc:
        logger.error("Agent cycle timeout: %s", exc)
        result = _make_result(False, "That took too long. Please try a simpler request.", str(exc), "intent:timeout")
    except Exception as exc:
        logger.exception("Unexpected agent cycle error: %s", exc)
        result = _make_result(False, "Something went wrong. I've logged the error.", str(exc), "intent:error")

    fallback_decision = decision or {
        "type": "intent",
        "name": (intent.name.value if intent else "error"),
        "confidence": (intent.confidence if intent else 0.0),
        "requires_plan": False,
    }
    response_text = str(result.get("output") or "")
    evaluation_obj = evaluate(
        output=response_text,
        original_input=user_input,
        intent_name=str(fallback_decision.get("intent") or fallback_decision.get("name") or ""),
        use_llm=False,
    )
    evaluation = _evaluation_payload(evaluation_obj)
    if isinstance(result.get("output"), str):
        result["output"] = clean_response(result["output"], fallback_decision)
    clean = clean_response(str(result.get("output") or ""), fallback_decision)
    state.add_to_conversation(role="user", content=user_input)
    state.add_to_conversation(role="assistant", content=clean)
    update_state(state, result, evaluation)
    trace = _build_trace(observation, fallback_decision, [], result, evaluation, error=result.get("error"))
    if emit_trace:
        _print_trace(cycle, trace)
    return result, evaluation, trace, state


async def run_agent_loop(
    state: State | None = None,
    memory: Memory | None = None,
) -> State:
    current_state = state or State()
    current_memory = memory or Memory()
    cycle = 0

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in EXIT_COMMANDS:
                logger.info("Exiting agent loop.")
                break

            cycle += 1
            await run_agent_cycle(user_input, current_memory, current_state, emit_trace=True, cycle=cycle)
        except KeyboardInterrupt:
            logger.info("Exiting agent loop.")
            break
        except Exception as exc:
            cycle += 1
            error_text = str(exc)
            current_state.errors.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "error": error_text,
                }
            )
            current_state.errors = current_state.errors[-10:]
            _print_trace(cycle, _build_trace(None, None, [], None, None, error=error_text))

    return current_state


if __name__ == "__main__":
    asyncio.run(run_agent_loop())
