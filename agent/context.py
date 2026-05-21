"""
agent/context.py

Context Budget Manager for Jarvis.
Assembles LLM prompts within a hard token budget.
Uses character-based estimation (4 chars ~= 1 token) for zero-overhead budgeting.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("jarvis.context")

CHARS_PER_TOKEN = 4
DEFAULT_BUDGET_TOKENS = 4000
SYSTEM_PROMPT_RESERVE = 500
RESPONSE_RESERVE = 500


@dataclass
class ContextBudget:
    total_tokens: int = DEFAULT_BUDGET_TOKENS
    system_reserve: int = SYSTEM_PROMPT_RESERVE
    response_reserve: int = RESPONSE_RESERVE

    @property
    def available_tokens(self) -> int:
        return self.total_tokens - self.system_reserve - self.response_reserve


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


class ContextBuilder:
    """
    Assembles a prompt from components within a token budget.
    Priority order (highest to lowest):
      1. Current user input
      2. Relevant memory entries
      3. Recent conversation history
      4. State context
    """

    def __init__(self, budget: ContextBudget = None):
        self._budget = budget or ContextBudget()
        self._components: list[tuple[int, str, str]] = []

    def add(self, label: str, text: str, priority: int) -> "ContextBuilder":
        if text and text.strip():
            self._components.append((priority, label, text.strip()))
        return self

    def build(self) -> str:
        self._components.sort(key=lambda x: x[0])
        remaining = self._budget.available_tokens
        parts = []

        for priority, label, text in self._components:
            tokens_needed = _estimate_tokens(text)
            if tokens_needed <= remaining:
                parts.append(f"[{label}]\n{text}")
                remaining -= tokens_needed
            elif remaining > 50:
                truncated = _truncate_to_tokens(text, remaining - 10)
                parts.append(f"[{label} - truncated]\n{truncated}")
                remaining = 0
                break
            else:
                logger.debug("Context budget exhausted, dropping: %s", label)
                break

        return "\n\n".join(parts)


def build_decide_context(user_input: str, memory_entries: list[dict], state) -> str:
    """
    Build minimal context for decide() calls.
    Tuned for low token use and routing only.
    """
    builder = ContextBuilder()
    builder.add("USER INPUT", user_input, priority=1)

    if memory_entries:
        mem_text = "\n".join(
            f"- {str(entry.get('content', ''))[:200]}"
            for entry in memory_entries[:3]
        )
        builder.add("RELEVANT MEMORY", mem_text, priority=2)

    recent = state.get_recent_conversation(n=2) if hasattr(state, "get_recent_conversation") else []
    if recent:
        hist = "\n".join(
            f"{str(message.get('role', '')).upper()}: {str(message.get('content', ''))[:150]}"
            for message in recent
        )
        builder.add("RECENT HISTORY", hist, priority=3)

    active_app = getattr(state, "active_app", "") or "none"
    mode = getattr(state, "mode", "fast")
    builder.add("STATE", f"active_app={active_app} mode={mode}", priority=4)

    return builder.build()


def build_act_context(user_input: str, memory_entries: list[dict], state, decision: dict) -> str:
    """
    Build context for act() response generation.
    More generous than decision context, but still bounded.
    """
    budget = ContextBudget(total_tokens=1600)
    builder = ContextBuilder(budget=budget)

    builder.add("USER INPUT", user_input, priority=1)
    builder.add(
        "TASK",
        f"type={decision.get('type')} name={decision.get('name')}",
        priority=2,
    )

    if memory_entries:
        mem_text = "\n".join(
            f"- {str(entry.get('content', ''))[:300]}"
            for entry in memory_entries[:5]
        )
        builder.add("RELEVANT MEMORY", mem_text, priority=3)

    recent = state.get_recent_conversation(n=4) if hasattr(state, "get_recent_conversation") else []
    if recent:
        hist = "\n".join(
            f"{str(message.get('role', '')).upper()}: {str(message.get('content', ''))[:200]}"
            for message in recent
        )
        builder.add("RECENT HISTORY", hist, priority=4)

    active_app = getattr(state, "active_app", "") or "none"
    mode = getattr(state, "mode", "fast")
    search_engine = getattr(state, "search_engine", "google")
    state_snapshot = (
        f"active_app={active_app} "
        f"mode={mode} "
        f"search_engine={search_engine}"
    )
    builder.add("STATE", state_snapshot, priority=5)

    return builder.build()


def build_plan_context(goal: str, state) -> str:
    """Minimal context for planner: goal + recent two turns + compact state."""
    builder = ContextBuilder(ContextBudget(total_tokens=800))
    builder.add("GOAL", goal, priority=1)

    recent = state.get_recent_conversation(n=2) if hasattr(state, "get_recent_conversation") else []
    if recent:
        hist = "\n".join(
            f"{str(message.get('role', '')).upper()}: {str(message.get('content', ''))[:100]}"
            for message in recent
        )
        builder.add("RECENT HISTORY", hist, priority=2)

    active_app = getattr(state, "active_app", "") or "none"
    mode = getattr(state, "mode", "fast")
    builder.add("STATE", f"active_app={active_app} mode={mode}", priority=3)
    return builder.build()

