from __future__ import annotations

from typing import Any


def observe(user_input: Any, memory: Any, state: Any) -> dict[str, Any]:
    mode = getattr(state, "mode", "smart")
    memory_context = memory.retrieve(user_input, mode=mode, limit=5) if memory is not None else {}
    if memory is not None and hasattr(memory, "is_semantic_available"):
        try:
            if memory.is_semantic_available():
                semantic = memory.search_semantic(user_input, top_k=5)
                if isinstance(memory_context, list) and len(memory_context) < 3:
                    existing = {entry.get("content", "")[:50] for entry in memory_context}
                    for semantic_entry in semantic:
                        if semantic_entry.get("content", "")[:50] not in existing:
                            memory_context.append(semantic_entry)
                    memory_context = memory_context[:5]
                elif isinstance(memory_context, dict):
                    matches = list(memory_context.get("matches", []) or [])
                    if len(matches) < 3:
                        existing = {entry.get("content", "")[:50] for entry in matches}
                        for semantic_entry in semantic:
                            if semantic_entry.get("content", "")[:50] not in existing:
                                matches.append(semantic_entry)
                        memory_context = {**memory_context, "matches": matches[:5]}
        except Exception:
            pass
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
