from __future__ import annotations

from typing import Any


def observe(user_input: Any, memory: Any, state: Any) -> dict[str, Any]:
    return {
        "input": user_input,
        "memory": memory.retrieve(user_input),
        "state": state,
        "recent_history": list(getattr(state, "history", []))[-3:],
    }
