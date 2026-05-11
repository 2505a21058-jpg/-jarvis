from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from agent.act import act
from agent.decide import decide
from agent.evaluate import EvaluationResult, evaluate
from agent.gate import GateDecision, get_gate
from agent.learn import learn
from agent.observe import observe
from agent.planner import Plan, _needs_plan, plan as make_plan
from agent.response_cleaner import clean_response
from agent.state import State, update_state
from memory.core import Memory
from skills.registry import SkillRegistry


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


def _serialize_plan(plan_obj: Plan | None) -> list[dict[str, Any]]:
    if plan_obj is None:
        return []
    return [
        {
            "index": step.index,
            "skill_name": step.skill_name,
            "description": step.description,
            "params": dict(step.params or {}),
            "depends_on": list(step.depends_on or []),
            "output_key": step.output_key,
            "success": step.success,
            "error": step.error,
        }
        for step in list(plan_obj.steps or [])
    ]


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
    emit_trace: bool = False,
    cycle: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], State]:
    result = dict(result or {})
    if isinstance(result.get("output"), str):
        result["output"] = clean_response(result["output"], decision)

    evaluation_obj = evaluation_result or evaluate(result, decision, state)
    evaluation = _evaluation_payload(evaluation_obj)
    learn(observation or {"input": user_input}, decision, result, evaluation, memory=memory)
    clean = clean_response(str(result.get("output") or ""), decision)
    state.add_to_conversation(role="user", content=user_input)
    state.add_to_conversation(role="assistant", content=clean)
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


def _gate_result(decision: GateDecision, state: State) -> dict[str, Any]:
    route_decision = {
        "type": "gate",
        "name": decision.skill_name or "direct_response",
        "confidence": decision.confidence,
        "reason": f"Gate rule: {decision.rule_id}",
        "requires_plan": False,
        "rule_id": decision.rule_id,
    }

    if decision.skill_name == "__direct_response__":
        response = decision.direct_response or str(decision.params.get("response", "")).strip()
        result = {
            "success": True,
            "output": response,
            "error": None,
            "steps": [
                {
                    "attempt": 1,
                    "action": "gate:direct_response",
                    "success": True,
                    "error": None,
                }
            ],
        }
        result["decision"] = {
            "type": route_decision["type"],
            "name": route_decision["name"],
            "confidence": route_decision["confidence"],
            "requires_plan": route_decision["requires_plan"],
        }
        return {"decision": route_decision, "result": result}

    registry = SkillRegistry.instance()
    skill_result = registry.execute(decision.skill_name, decision.params, state)
    output = skill_result.output if skill_result.success else f"Error: {skill_result.error}"
    result = {
        "success": skill_result.success,
        "output": output,
        "error": None if skill_result.success else skill_result.error,
        "steps": [
            {
                "attempt": 1,
                "action": f"gate:{decision.skill_name}",
                "success": skill_result.success,
                "error": skill_result.error,
                "duration_ms": round(skill_result.duration_ms, 2),
            }
        ],
    }
    result["decision"] = {
        "type": route_decision["type"],
        "name": route_decision["name"],
        "confidence": route_decision["confidence"],
        "requires_plan": route_decision["requires_plan"],
    }
    return {"decision": route_decision, "result": result}


def run_agent_cycle(
    user_input: str,
    memory: Memory,
    state: State,
    *,
    emit_trace: bool = False,
    cycle: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], State]:
    observation: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    execution_plan: list[dict[str, Any]] = []
    plan_obj: Plan | None = None

    try:
        try:
            from memory.personal_facts import store_fact

            stored_fact = store_fact(user_input)
            if stored_fact:
                logger.info("Personal fact detected and stored: %s", stored_fact)
        except Exception as exc:
            logger.debug("Personal fact pre-store skipped: %s", exc)

        gate = get_gate()
        gate_decision = gate.evaluate(user_input)
        if gate_decision.resolved:
            if gate_decision.skill_name == "__recall_facts__":
                from memory.personal_facts import format_facts_for_llm, get_all_facts

                facts = get_all_facts()
                if facts:
                    response = format_facts_for_llm(facts).replace(
                        "Personal facts about the user:",
                        "Here is what I remember about you:",
                    )
                else:
                    response = (
                        "I don't have any personal facts stored about you yet. "
                        "Tell me something like 'remember I like coffee' and I'll remember it."
                    )
                recall_decision = {
                    "type": "gate",
                    "name": "__recall_facts__",
                    "confidence": gate_decision.confidence,
                    "reason": f"Gate rule: {gate_decision.rule_id}",
                    "requires_plan": False,
                    "rule_id": gate_decision.rule_id,
                }
                recall_result = {
                    "success": True,
                    "output": response,
                    "error": None,
                    "steps": [
                        {
                            "attempt": 1,
                            "action": "gate:recall_facts",
                            "success": True,
                            "error": None,
                        }
                    ],
                    "decision": {
                        "type": "gate",
                        "name": "__recall_facts__",
                        "confidence": gate_decision.confidence,
                        "requires_plan": False,
                    },
                }
                recall_observation = {
                    "input": user_input,
                    "gate": {
                        "rule_id": gate_decision.rule_id,
                        "skill_name": gate_decision.skill_name,
                        "params": dict(gate_decision.params),
                        "confidence": gate_decision.confidence,
                    },
                }
                return _post_cycle(
                    user_input,
                    recall_result,
                    recall_decision,
                    memory,
                    state,
                    source="gate",
                    observation=recall_observation,
                    execution_plan=[],
                    emit_trace=emit_trace,
                    cycle=cycle,
                )

            gate_observation = {
                "input": user_input,
                "gate": {
                    "rule_id": gate_decision.rule_id,
                    "skill_name": gate_decision.skill_name,
                    "params": dict(gate_decision.params),
                    "confidence": gate_decision.confidence,
                },
            }
            gate_payload = _gate_result(gate_decision, state)
            return _post_cycle(
                user_input,
                gate_payload["result"],
                gate_payload["decision"],
                memory,
                state,
                source="gate",
                observation=gate_observation,
                execution_plan=[],
                emit_trace=emit_trace,
                cycle=cycle,
            )

        from agent.complexity_scorer import compute_complexity_score
        from agent.fast_decide import fast_decide

        _complexity = compute_complexity_score(user_input)
        logger.debug("Complexity score: %s", _complexity)
        if not _complexity["escalate"]:
            tier2_decision = fast_decide(user_input)
            if tier2_decision is not None:
                tier2_execution = dict(tier2_decision)
                tier2_execution["_state_obj"] = state
                tier2_execution["_memory_obj"] = memory
                result = act(tier2_execution, memory, state, plan=None)
                result["decision"] = {
                    "type": tier2_decision.get("type"),
                    "name": tier2_decision.get("name"),
                    "confidence": tier2_decision.get("confidence"),
                    "requires_plan": tier2_decision.get("requires_plan"),
                }
                tier2_observation = {
                    "input": user_input,
                    "tier": "fast_decide",
                }
                return _post_cycle(
                    user_input,
                    result,
                    tier2_decision,
                    memory,
                    state,
                    source="tier2",
                    observation=tier2_observation,
                    execution_plan=[],
                    emit_trace=emit_trace,
                    cycle=cycle,
                )

        observation = observe(user_input, memory, state)
        decision = decide(observation)
        if _needs_plan(decision):
            plan_obj = make_plan(decision, state, memory)
            execution_plan = _serialize_plan(plan_obj)
        else:
            execution_plan = []

        execution_input = dict(decision)
        execution_input["_state_obj"] = state
        execution_input["_memory_obj"] = memory
        final_decision = decision
        final_evaluation: EvaluationResult | None = None
        result = act(execution_input, memory, state, plan=plan_obj)

        if plan_obj is None:
            eval_result = evaluate(result, decision, state)
            decision_parameters = decision.get("parameters", {})
            if not isinstance(decision_parameters, dict):
                decision_parameters = {}

            if (
                eval_result.should_replan
                and decision.get("type") in ("skill",)
                and not decision.get("_retry_attempt", False)
            ):
                logger.warning(
                    "Evaluation flagged failure (score=%.2f, type=%s). Attempting single auto-retry.",
                    eval_result.score,
                    eval_result.failure_type,
                )
                retry_decision = {
                    **decision,
                    "_retry_attempt": True,
                    "parameters": {
                        **decision_parameters,
                        "_failure_context": eval_result.failure_type or "unknown",
                    },
                }
                retry_input = dict(retry_decision)
                retry_input["_state_obj"] = state
                retry_input["_memory_obj"] = memory
                retry_response = act(retry_input, memory, state, plan=None)
                retry_eval = evaluate(retry_response, retry_decision, state)

                if retry_eval.passed:
                    logger.info("Auto-retry succeeded.")
                    result = retry_response
                    final_decision = retry_decision
                    final_evaluation = retry_eval
                else:
                    logger.warning("Auto-retry also failed. Returning best available response.")
                    final_evaluation = eval_result
                    if retry_eval.score > eval_result.score:
                        result = retry_response
                        final_decision = retry_decision
                        final_evaluation = retry_eval
            else:
                final_evaluation = eval_result

        if plan_obj is not None:
            execution_plan = _serialize_plan(plan_obj)
        result["decision"] = {
            "type": final_decision.get("type"),
            "name": final_decision.get("name"),
            "confidence": final_decision.get("confidence"),
            "requires_plan": final_decision.get("requires_plan"),
        }
        return _post_cycle(
            user_input,
            result,
            final_decision,
            memory,
            state,
            source="agent",
            observation=observation,
            execution_plan=execution_plan,
            evaluation_result=final_evaluation,
            emit_trace=emit_trace,
            cycle=cycle,
        )
    except RuntimeError as exc:
        logger.error("Agent cycle LLM failure: %s", exc)
        result = {
            "success": False,
            "output": "I encountered a model error. Please try again.",
            "error": str(exc),
            "steps": [],
        }
    except TimeoutError as exc:
        logger.error("Agent cycle timeout: %s", exc)
        result = {
            "success": False,
            "output": "That took too long. Please try a simpler request.",
            "error": str(exc),
            "steps": [],
        }
    except Exception as exc:
        logger.exception("Unexpected agent cycle error: %s", exc)
        result = {
            "success": False,
            "output": "Something went wrong. I've logged the error.",
            "error": str(exc),
            "steps": [],
        }

    fallback_decision = decision or {
        "type": "llm",
        "name": "error",
        "confidence": 0.0,
        "requires_plan": False,
    }
    result["decision"] = {
        "type": fallback_decision.get("type"),
        "name": fallback_decision.get("name"),
        "confidence": fallback_decision.get("confidence"),
        "requires_plan": fallback_decision.get("requires_plan"),
    }
    evaluation_obj = evaluate(result, fallback_decision, state)
    evaluation = _evaluation_payload(evaluation_obj)
    if isinstance(result.get("output"), str):
        result["output"] = clean_response(result["output"], fallback_decision)
    clean = clean_response(str(result.get("output") or ""), fallback_decision)
    state.add_to_conversation(role="user", content=user_input)
    state.add_to_conversation(role="assistant", content=clean)
    update_state(state, result, evaluation)
    trace = _build_trace(observation, fallback_decision, execution_plan, result, evaluation, error=result.get("error"))
    if emit_trace:
        _print_trace(cycle, trace)
    return result, evaluation, trace, state


def run_agent_loop(
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
            run_agent_cycle(user_input, current_memory, current_state, emit_trace=True, cycle=cycle)
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
    run_agent_loop()
