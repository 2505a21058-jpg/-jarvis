from __future__ import annotations

import json
from datetime import datetime
from typing import Any


EXIT_COMMANDS = {"quit", "exit", "bye"}


def create_initial_state() -> dict[str, Any]:
    return {
        "current_task": None,
        "last_action": None,
        "last_result": None,
        "history": [],
        "errors": [],
    }


def observe(user_input: str, memory: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": str(user_input).strip(),
        "memory_context": memory or {},
        "state": dict(state),
        "recent_history": list(state.get("history", []))[-5:],
    }


def decide(observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "llm",
        "name": "placeholder",
        "confidence": 0.0,
        "reason": "Decision placeholder",
        "requires_plan": False,
        "observation_input": observation.get("input", ""),
    }


def act(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "output": None,
        "error": None,
        "steps": [],
        "decision": dict(decision),
    }


def evaluate(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "quality_score": 1.0 if result.get("success") else 0.0,
        "error": result.get("error"),
        "retry_recommended": False,
        "decision_type": decision.get("type"),
    }


def learn(
    observation: dict[str, Any],
    decision: dict[str, Any],
    result: dict[str, Any],
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(),
        "input": observation.get("input", ""),
        "decision": dict(decision),
        "result_success": result.get("success"),
        "evaluation": dict(evaluation),
    }


def update_state(state: dict[str, Any], result: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    state["last_action"] = result.get("decision", {}).get("name")
    state["last_result"] = result
    state["current_task"] = None
    state.setdefault("history", []).append(
        {
            "timestamp": datetime.now().isoformat(),
            "success": result.get("success"),
            "evaluation": evaluation,
        }
    )
    state["history"] = state["history"][-10:]

    if evaluation.get("error"):
        state.setdefault("errors", []).append(
            {
                "timestamp": datetime.now().isoformat(),
                "error": evaluation.get("error"),
            }
        )
        state["errors"] = state["errors"][-10:]

    return state


def _build_trace(
    observation: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    result: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "input": (observation or {}).get("input", ""),
        "observation": observation or {},
        "decision": decision or {},
        "result": result or {},
        "evaluation": evaluation or {},
        "error": error,
    }


def _print_trace(cycle: int, trace: dict[str, Any]):
    print(f"[Agent] Cycle {cycle}")
    print(json.dumps(trace, indent=2, ensure_ascii=True, default=str))


def run_agent_loop(
    state: dict[str, Any] | None = None,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_state = state or create_initial_state()
    cycle = 0

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in EXIT_COMMANDS:
                print("Exiting agent loop.")
                break

            cycle += 1
            observation = observe(user_input, memory, current_state)
            decision = decide(observation)
            result = act(decision)
            evaluation = evaluate(result, decision)
            learn(observation, decision, result, evaluation)
            current_state = update_state(current_state, result, evaluation)
            _print_trace(cycle, _build_trace(observation, decision, result, evaluation))
        except KeyboardInterrupt:
            print("\nExiting agent loop.")
            break
        except Exception as exc:
            error_text = str(exc)
            current_state.setdefault("errors", []).append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "error": error_text,
                }
            )
            current_state["errors"] = current_state["errors"][-10:]
            cycle += 1
            _print_trace(cycle, _build_trace(None, None, None, None, error=error_text))

    return current_state


if __name__ == "__main__":
    run_agent_loop()
