from __future__ import annotations

import asyncio

from interfaces.remote_bridge import (
    _AUTHORIZED_CHAT_IDS,
    _handle_remote_input,
    _is_high_risk,
    _pending_approvals,
    _run_cycle,
)


def test_remote_bridge_awaits_async_agent_cycle(monkeypatch):
    state = object()

    async def fake_run_agent_cycle(user_input, memory, state_arg):
        assert user_input == "remote hello"
        assert state_arg is state
        return ({"output": "remote ok"}, {}, {}, state_arg)

    monkeypatch.setattr("agent.loop.run_agent_cycle", fake_run_agent_cycle)

    response = asyncio.run(_run_cycle("remote hello", object(), state))

    assert response == "remote ok"


def test_remote_bridge_flags_agent_and_file_control_as_high_risk():
    assert _is_high_risk("run_code to parse this data") is True
    assert _is_high_risk("read_file C:/Users/example/.env") is True
    assert _is_high_risk("search my whole computer for password") is True
    assert _is_high_risk("use computer_control to finish this") is True


def test_remote_approve_grants_one_policy_approval(monkeypatch):
    chat_id = 42
    responses = []

    class State:
        active_app = ""
        mode = "fast"
        conversation_history = []

        def __init__(self):
            self.ui_context = {}

    state = State()
    _AUTHORIZED_CHAT_IDS.add(chat_id)
    _pending_approvals.clear()
    _pending_approvals[f"{chat_id}:run_code to parse this data"] = {
        "input": "run_code to parse this data",
        "chat_id": chat_id,
    }

    async def fake_run_cycle(user_input, memory, state_arg):
        assert user_input == "run_code to parse this data"
        assert state_arg.ui_context["policy_approvals"] == ["*"]
        return "approved"

    async def responder(text):
        responses.append(text)

    monkeypatch.setattr("interfaces.remote_bridge._run_cycle", fake_run_cycle)

    try:
        asyncio.run(_handle_remote_input("/approve", chat_id, responder, object(), state))
    finally:
        _AUTHORIZED_CHAT_IDS.discard(chat_id)
        _pending_approvals.clear()

    assert responses == ["Executing: run_code to parse this data", "Processing...", "approved"]
