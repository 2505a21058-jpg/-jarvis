from __future__ import annotations

import os

from agent.loop import run_agent_cycle


def test_run_agent_cycle_sets_runtime_env_var(monkeypatch, memory, state):
    monkeypatch.delenv("JARVIS_VISION_VERIFY", raising=False)
    monkeypatch.setattr("agent.loop.learn", lambda *args, **kwargs: None)

    result, evaluation, trace, updated_state = run_agent_cycle(
        "set JARVIS_VISION_VERIFY=true",
        memory,
        state,
    )

    assert result["success"] is True
    assert "Set JARVIS_VISION_VERIFY=true for this session." in result["output"]
    assert "In PowerShell, 'set X=Y' creates a PowerShell variable" in result["output"]
    assert "Use instead: $env:JARVIS_VISION_VERIFY = \"true\"" in result["output"]
    assert os.environ["JARVIS_VISION_VERIFY"] == "true"
    assert evaluation["success"] is True
    assert trace["decision"]["name"] == "__set_env__"
    assert updated_state.conversation_history[-1]["content"] == result["output"]
