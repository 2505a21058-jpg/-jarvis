from __future__ import annotations

import asyncio
import os

from agent.executor import ExecutionResult
from agent.evaluate import EvaluationResult
from agent.intent.schema import Entity, Intent, IntentName
from agent.loop import _make_result, _post_cycle, run_agent_cycle


def test_run_agent_cycle_sets_runtime_env_var(monkeypatch, memory, state):
    monkeypatch.setenv("JARVIS_VISION_VERIFY", "")
    monkeypatch.delenv("JARVIS_VISION_VERIFY", raising=False)
    monkeypatch.setattr("agent.loop.learn", lambda *args, **kwargs: None)

    result, evaluation, trace, updated_state = asyncio.run(
        run_agent_cycle(
            "set JARVIS_VISION_VERIFY=true",
            memory,
            state,
        )
    )

    assert result["success"] is True
    assert "Set JARVIS_VISION_VERIFY=true" in result["output"]
    assert "saved to jconfig.yaml" in result["output"]
    assert os.environ["JARVIS_VISION_VERIFY"] == "true"
    assert evaluation["success"] is True
    assert trace["decision"]["name"] == "__set_env__"
    assert updated_state.conversation_history[-1]["content"] == result["output"]


def test_run_agent_cycle_executes_gemma_plan_for_automation_intent(monkeypatch, memory, state):
    import agent.loop as loop
    import skills.automation.gemma_bridge as gemma_bridge

    monkeypatch.setattr(loop, "learn", lambda *args, **kwargs: None)
    monkeypatch.setattr(loop, "get_model_for_intent", lambda intent_name: "gemma")
    monkeypatch.setattr(
        loop,
        "classify",
        lambda raw: Intent(
            name=IntentName.OPEN_APP,
            entities={"app": Entity(name="app", value="chrome")},
            confidence=1.0,
            raw_input=raw,
            classification_source="rule",
        ),
    )
    monkeypatch.setattr(
        gemma_bridge,
        "plan_automation",
        lambda raw: [{"skill": "open_app", "params": {"app": "chrome"}}],
    )

    calls = []

    class FakeExecutor:
        async def execute_async(self, skill_name, params, state_arg, step_index=0, **kwargs):
            calls.append((skill_name, params, state_arg, step_index))
            return ExecutionResult(
                success=True,
                output="Opened chrome",
                elapsed_ms=1.0,
                duration_ms=1.0,
                skill_name=skill_name,
                step_index=step_index,
                verified=True,
            )

    monkeypatch.setattr("agent.executor.get_executor", lambda: FakeExecutor())

    result, evaluation, trace, updated_state = asyncio.run(
        run_agent_cycle(
            "open chrome",
            memory,
            state,
        )
    )

    assert result["success"] is True
    assert result["output"] == "Opened chrome"
    assert evaluation["success"] is True
    assert trace["decision"]["model"] == "gemma"
    assert trace["plan"] == [{"index": 1, "skill": "open_app", "params": {"app": "chrome"}}]
    assert calls == [("open_app", {"app": "chrome"}, state, 1)]
    assert updated_state.conversation_history[-1]["content"] == "Opened chrome"


def test_run_agent_cycle_stats_bypasses_intent_classification(monkeypatch, memory, state):
    import agent.loop as loop

    monkeypatch.setattr(
        loop,
        "classify",
        lambda raw: (_ for _ in ()).throw(AssertionError("stats should not classify intent")),
    )
    monkeypatch.setattr(loop, "learn", lambda *args, **kwargs: None)

    result, evaluation, trace, updated_state = asyncio.run(run_agent_cycle("/stats", memory, state))

    assert result["success"] is True
    assert "Jarvis Diagnostics" in result["output"]
    assert "Intent:" in result["output"]
    assert "Executor:" in result["output"]
    assert "Memory:" in result["output"]
    assert evaluation["success"] is True
    assert trace["decision"]["name"] == "__diagnostics__"
    assert updated_state.conversation_history[-1]["content"] == result["output"]


def test_run_agent_cycle_executes_learned_rule_without_model_router(monkeypatch, memory, state):
    import agent.loop as loop

    calls = []

    monkeypatch.setattr(loop, "learn", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        loop,
        "get_model_for_intent",
        lambda intent_name: (_ for _ in ()).throw(AssertionError("learned rules should bypass model routing")),
    )
    monkeypatch.setattr(
        loop,
        "classify",
        lambda raw: Intent(
            name=IntentName.UNKNOWN,
            entities={"__learned_skill__": Entity(name="__learned_skill__", value="open_dev_setup")},
            confidence=1.0,
            raw_input=raw,
            classification_source="learned_rule",
        ),
    )

    class FakeExecutor:
        async def execute_async(self, skill_name, params, state_arg, **kwargs):
            calls.append((skill_name, params, state_arg))
            return ExecutionResult(
                success=True,
                output="Dev setup opened",
                elapsed_ms=1.0,
                duration_ms=1.0,
                skill_name=skill_name,
                verified=True,
            )

    monkeypatch.setattr("agent.executor.get_executor", lambda: FakeExecutor())

    result, evaluation, trace, updated_state = asyncio.run(
        run_agent_cycle("open my dev setup", memory, state)
    )

    assert result["success"] is True
    assert result["output"] == "Dev setup opened"
    assert evaluation["success"] is True
    assert trace["decision"]["classification_source"] == "learned_rule"
    assert calls == [("open_dev_setup", {}, state)]
    assert updated_state.conversation_history[-1]["content"] == "Dev setup opened"


def test_post_cycle_calls_new_evaluator_api_for_long_llm_response(monkeypatch, memory, state):
    import agent.loop as loop

    calls = []

    def fake_evaluate(**kwargs):
        calls.append(kwargs)
        return EvaluationResult(success=True, confidence=0.82, source="rule")

    monkeypatch.setattr(loop, "evaluate", fake_evaluate)
    monkeypatch.setattr(loop, "learn", lambda *args, **kwargs: None)

    response = "This is a long enough LLM response that should opt into quality evaluation."
    result, evaluation, trace, updated_state = _post_cycle(
        "explain something",
        _make_result(True, response, action="intent:respond"),
        {
            "type": "intent",
            "name": "respond",
            "intent": "chat",
            "confidence": 1.0,
            "requires_plan": False,
        },
        memory,
        state,
        source="intent_llm",
    )

    assert calls == [
        {
            "output": response,
            "original_input": "explain something",
            "intent_name": "chat",
            "use_llm": True,
            "exec_success": None,
        }
    ]
    assert evaluation["confidence"] == 0.82
    assert updated_state.ui_context["last_eval_confidence"] == 0.82
    assert trace["evaluation"]["source"] == "rule"
