from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _timestamp() -> str:
    return datetime.now().isoformat()


@dataclass
class State:
    mode: str = "fast"
    current_task: Any = None
    last_action: Any = None
    last_result: Any = None
    active_app: str = ""
    active_platform: str = "default"
    search_engine: str = "google"
    browser_url: str = ""
    clipboard: str = ""
    ui_context: dict[str, Any] = field(default_factory=dict)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    task_stack: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "current_task": self.current_task,
            "last_action": self.last_action,
            "last_result": self.last_result,
            "active_app": self.active_app,
            "active_platform": self.active_platform,
            "search_engine": self.search_engine,
            "browser_url": self.browser_url,
            "clipboard": self.clipboard,
            "ui_context": dict(self.ui_context),
            "conversation_history": list(self.conversation_history),
            "task_stack": list(self.task_stack),
            "history": list(self.history),
            "errors": list(self.errors),
        }

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key, default)
        return self.ui_context.get(key, default)

    def set_active_app(self, app_name: str) -> None:
        normalized = str(app_name or "").strip().lower()
        self.active_app = normalized
        self.active_platform = normalized or "default"

    def get_active_app(self) -> str:
        return self.active_app

    def set_search_engine(self, engine: str) -> None:
        self.search_engine = str(engine or "").strip().lower() or "google"

    def get_search_engine(self) -> str:
        return self.search_engine

    def set_clipboard(self, text: str) -> None:
        self.clipboard = str(text or "")

    def get_clipboard(self) -> str:
        return self.clipboard

    def push_task(self, task: dict) -> None:
        if isinstance(task, dict):
            self.task_stack.append(task)

    def pop_task(self) -> dict | None:
        return self.task_stack.pop() if self.task_stack else None

    def add_to_conversation(self, role: str, content: str) -> None:
        text = str(content or "").strip()
        if not text:
            return
        self.conversation_history.append({"role": str(role or "").strip(), "content": text})
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

    def get_recent_conversation(self, n: int = 10) -> list[dict]:
        count = max(int(n or 0), 0)
        if count <= 0:
            return []
        return list(self.conversation_history[-count:])

    def to_context_dict(self) -> dict:
        """Returns a serializable snapshot of current state for LLM context."""
        return {
            "mode": self.mode,
            "active_app": self.active_app,
            "active_platform": self.active_platform,
            "search_engine": self.search_engine,
            "browser_url": self.browser_url,
            "task_stack_depth": len(self.task_stack),
        }

    def record_plan_execution(self, plan) -> None:
        """Record a completed or failed plan for learning/debugging."""
        self.ui_context["last_plan"] = {
            "goal": getattr(plan, "goal", ""),
            "steps_count": len(getattr(plan, "steps", []) or []),
            "completed": bool(getattr(plan, "completed", False)),
            "failed": bool(getattr(plan, "failed", False)),
            "failure_reason": getattr(plan, "failure_reason", None),
        }


def add_to_history(state: State, user_input: Any, output: Any) -> State:
    state.history.append(
        {
            "timestamp": _timestamp(),
            "input": user_input,
            "output": output,
        }
    )
    state.history = state.history[-10:]
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
        state.errors = state.errors[-10:]

    return state
