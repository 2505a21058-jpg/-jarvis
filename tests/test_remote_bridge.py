from __future__ import annotations

import asyncio

from interfaces.remote_bridge import _run_cycle


def test_remote_bridge_awaits_async_agent_cycle(monkeypatch):
    state = object()

    async def fake_run_agent_cycle(user_input, memory, state_arg):
        assert user_input == "remote hello"
        assert state_arg is state
        return ({"output": "remote ok"}, {}, {}, state_arg)

    monkeypatch.setattr("agent.loop.run_agent_cycle", fake_run_agent_cycle)

    response = asyncio.run(_run_cycle("remote hello", object(), state))

    assert response == "remote ok"
