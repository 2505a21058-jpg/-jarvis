"""Tests for AgentSkill — ReAct loop with native Ollama tool calling."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from skills.base import SkillResult
from skills.catalog import AgentSkill, StepRunnerSkill, _TOOL_DEFS
from skills.manifest import SkillManifest


def _make_manifest(**overrides):
    defaults = dict(
        name="test-agent",
        description="A test agent skill",
        steps=[],
        instructions="Search for the given topic and summarize the results.",
    )
    defaults.update(overrides)
    return SkillManifest(**defaults)


def _tool_call(name: str, arguments: str, content: str | None = None):
    """Build a call_llm_tools return value with the given tool call."""
    return {
        "content": content,
        "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        "message": {"role": "assistant", "content": content, "tool_calls": []},
    }


def _text_response(text: str):
    """Build a call_llm_tools return value with text only."""
    return {
        "content": text,
        "tool_calls": None,
        "message": {"role": "assistant", "content": text},
    }


def _empty_response():
    return {"content": None, "tool_calls": None, "message": {}}


# ---------------------------------------------------------------------------
# Existing tests (adapted for the ReAct loop)
# ---------------------------------------------------------------------------


def test_no_instructions_returns_error():
    skill = AgentSkill(_make_manifest(instructions=""))
    result = skill.execute({"query": "test"}, None)
    assert not result.success
    assert "No instructions" in result.error


def test_llm_failure_returns_error():
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 1
    with patch("models.llm.call_llm_tools", return_value=_empty_response()):
        result = skill.execute({"query": "test"}, None)
    assert not result.success
    assert "LLM returned empty response" in result.error


def test_unknown_tool_returns_error():
    skill = AgentSkill(_make_manifest())
    call_count = [0]
    calls = [
        _tool_call("fly", "{}"),
        _text_response("The tool 'fly' does not exist."),
    ]

    def _side_effect(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return calls[idx] if idx < len(calls) else _text_response("Done")

    with patch("models.llm.call_llm_tools", side_effect=_side_effect):
        with patch("skills.app_helpers.STEP_FUNCS", {}):
            result = skill.execute({"query": "test"}, None)
    assert result.success
    assert "does not exist" in result.output


def test_answer_action():
    skill = AgentSkill(_make_manifest())
    with patch("models.llm.call_llm_tools", return_value=_text_response("Here are the results.")):
        result = skill.execute({"query": "test"}, None)
    assert result.success
    assert result.output == "Here are the results."


def test_tool_call_then_answer():
    """Agent calls a tool, gets result, then answers."""
    skill = AgentSkill(_make_manifest())

    call_count = [0]
    calls = [
        _tool_call("web_search", '{"query": "python testing"}'),
        _text_response("Python testing is a framework for..."),
    ]

    def _side_effect(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return calls[idx] if idx < len(calls) else _text_response("Done")

    with patch("models.llm.call_llm_tools", side_effect=_side_effect):
        with patch("internet.search.search", return_value=[]):
            result = skill.execute({"query": "test"}, None)

    assert result.success
    assert "Python testing" in result.output


def test_tool_call_dict_format():
    """Tool arguments as dict (not JSON string) is handled."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 1

    raw_return = {
        "content": None,
        "tool_calls": [
            {"function": {"name": "open", "arguments": {"app": "youtube.com"}}}
        ],
        "message": {},
    }

    executed = []

    with patch("models.llm.call_llm_tools", return_value=raw_return):
        with patch("skills.app_helpers.STEP_FUNCS", {
            "open": lambda p, ctx: (executed.append(p), True)[1],
        }):
            result = skill.execute({"query": "test"}, None)

    assert not result.success  # no final text answer after single tool call
    assert len(executed) == 1
    assert executed[0]["app"] == "youtube.com"


def test_unknown_step_returns_tool_error():
    """Unknown step names come back as tool errors."""
    skill = AgentSkill(_make_manifest())
    call_count = [0]
    calls = [
        _tool_call("nonexistent_step", "{}"),
        _text_response("That step is not available."),
    ]

    def _side_effect(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return calls[idx] if idx < len(calls) else _text_response("Done")

    with patch("models.llm.call_llm_tools", side_effect=_side_effect):
        with patch("skills.app_helpers.STEP_FUNCS", {}):
            result = skill.execute({"query": "test"}, None)

    assert result.success
    assert "not available" in result.output


def test_step_failure_returns_error():
    """STEP_FUNCS returns False => tool result has success:false."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 1

    with patch("models.llm.call_llm_tools", return_value=_tool_call("search", '{"query": "x"}')):
        with patch("skills.app_helpers.STEP_FUNCS", {
            "search": lambda p, ctx: False,
        }):
            result = skill.execute({"query": "test"}, None)

    assert not result.success


def test_inherits_step_runner_cleanup():
    """AgentSkill is a StepRunnerSkill and cleans up browser in finally."""
    skill = AgentSkill(_make_manifest())
    assert isinstance(skill, StepRunnerSkill)
    assert hasattr(skill, "_cleanup_browser")

    cleanup_called = False

    def _patched_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    skill._cleanup_browser = _patched_cleanup

    with patch("models.llm.call_llm_tools", return_value=_text_response("ok")):
        skill.execute({"query": "test"}, None)

    assert cleanup_called, "_cleanup_browser() should be called in finally block"


# ---------------------------------------------------------------------------
# New Phase 2 tests
# ---------------------------------------------------------------------------


def test_multi_turn_react():
    """Multiple tool calls in sequence before final answer."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 5

    call_count = [0]
    calls = [
        _tool_call("web_search", '{"query": "current weather London"}'),
        _tool_call("ask_llm", '{"prompt": "Summarize the weather data"}'),
        _text_response("The weather in London is 15°C and cloudy."),
    ]

    def _side_effect(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return calls[idx] if idx < len(calls) else _text_response("Done")

    with patch("models.llm.call_llm_tools", side_effect=_side_effect):
        with patch("internet.search.search", return_value=[]):
            with patch("models.llm.call_llm", return_value="15°C and cloudy"):
                result = skill.execute({"query": "test"}, None)

    assert result.success
    assert "15°C" in result.output
    assert call_count[0] == 3


def test_max_turns_exceeded():
    """Agent that keeps calling tools hits the turn limit."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 3

    tool_return = _tool_call("wait", '{"seconds": 1}')

    with patch("models.llm.call_llm_tools", return_value=tool_return):
        with patch("skills.app_helpers.STEP_FUNCS", {
            "wait": lambda p, ctx: True,
        }):
            result = skill.execute({"query": "test"}, None)

    assert not result.success
    assert "exceeded max turns" in result.error


def test_tool_error_continues_loop():
    """A tool that errors out can still be handled — the loop continues."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 3

    call_count = [0]
    calls = [
        _tool_call("run_code", '{"code": "1/0"}'),
        _text_response("The code raised a division by zero error."),
    ]

    def _side_effect(*a, **kw):
        idx = call_count[0]
        call_count[0] += 1
        return calls[idx] if idx < len(calls) else _text_response("Done")

    with patch("models.llm.call_llm_tools", side_effect=_side_effect):
        result = skill.execute({"query": "test"}, None)

    assert result.success
    assert "division by zero" in result.output
    assert call_count[0] == 2


def test_tool_content_pair():
    """LLM returns both content and tool_calls in one turn."""
    skill = AgentSkill(_make_manifest())
    skill.max_turns = 2

    response = {
        "content": "Let me search for that.",
        "tool_calls": [
            {"function": {"name": "web_search", "arguments": '{"query": "python"}'}}
        ],
        "message": {"role": "assistant", "content": "Let me search for that.", "tool_calls": []},
    }

    with patch("models.llm.call_llm_tools", return_value=response):
        with patch("internet.search.search", return_value=[]):
            result = skill.execute({"query": "test"}, None)

    # No final answer yet — just a tool call, so the loop continues but tool
    # result gets appended.  Since there's only one turn mocked and no answer,
    # we hit the tool call path but get stuck calling again and exceed turns.
    assert not result.success
    assert "exceeded max turns" in result.error


def test_tool_defs_contain_all_thirteen():
    """Verify _TOOL_DEFS has exactly 13 entries with expected names."""
    names = {t["function"]["name"] for t in _TOOL_DEFS}
    expected = {
        "open", "search", "select", "type", "play", "scroll",
        "shortcut", "wait", "close",
        "web_search", "run_code", "read_file", "ask_llm",
    }
    assert names == expected
    assert len(_TOOL_DEFS) == 13


def test_run_code_tool_routes_through_skill_executor():
    skill = AgentSkill(_make_manifest())
    calls = []
    state = {"mode": "fast"}

    class FakeExecutor:
        def execute(self, skill_name, params, passed_state):
            calls.append((skill_name, params, passed_state))
            return SimpleNamespace(success=False, output=None, error="Skill 'run_code' requires confirmation")

    with patch("agent.executor.get_executor", return_value=FakeExecutor()):
        result = skill._execute_tool("run_code", {"code": "result = 1"}, state)

    assert calls == [("run_code", {"code": "result = 1"}, state)]
    assert "requires confirmation" in result


def test_read_file_tool_routes_through_skill_executor():
    skill = AgentSkill(_make_manifest())
    calls = []
    state = {"mode": "fast"}

    class FakeExecutor:
        def execute(self, skill_name, params, passed_state):
            calls.append((skill_name, params, passed_state))
            return SimpleNamespace(success=False, output=None, error="Skill 'read_report' requires confirmation")

    with patch("agent.executor.get_executor", return_value=FakeExecutor()):
        result = skill._execute_tool("read_file", {"path": "C:/Users/example/.env"}, state)

    assert calls == [("read_report", {"path": "C:/Users/example/.env"}, state)]
    assert "requires confirmation" in result
