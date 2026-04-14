from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _timestamp() -> str:
    return datetime.now().isoformat()


@dataclass
class State:
    current_task: Any = None
    last_action: Any = None
    last_result: Any = None
    history: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_task": self.current_task,
            "last_action": self.last_action,
            "last_result": self.last_result,
            "history": list(self.history),
            "errors": list(self.errors),
        }


def add_to_history(state: State, user_input: Any, output: Any) -> State:
    state.history.append(
        {
            "timestamp": _timestamp(),
            "input": user_input,
            "output": output,
        }
    )
    return state


def update_state(state: State, result: dict[str, Any] | None, evaluation: dict[str, Any] | None) -> State:
    result = result or {}
    evaluation = evaluation or {}

    state.last_result = result
    state.last_action = result.get("decision", {}).get("name") or result.get("action")
    state.current_task = result.get("next_task")

    if evaluation.get("error"):
        state.errors.append(
            {
                "timestamp": _timestamp(),
                "error": evaluation.get("error"),
            }
        )

    return state
