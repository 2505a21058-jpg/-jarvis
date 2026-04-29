from __future__ import annotations

from typing import Any


def observe(user_input: Any, memory: Any, state: Any) -> dict[str, Any]:
    mode = getattr(state, "mode", "smart")
    memory_context = memory.retrieve(user_input, mode=mode) if memory is not None else {}
    state_payload = state.to_dict() if hasattr(state, "to_dict") else state
    recent_history = (
        state.get_recent_conversation(n=6)
        if hasattr(state, "get_recent_conversation")
        else list(getattr(state, "history", []))[-3:]
    )
    return {
        "input": user_input,
        "memory": memory_context,
        "state": state_payload,
        "state_obj": state,
        "recent_history": recent_history,
    }
