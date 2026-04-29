from __future__ import annotations

import pytest

from agent.evaluate import evaluate


@pytest.fixture
def skill_decision():
    return {"type": "skill", "name": "open_app"}


def test_empty_fails(state, skill_decision):
    result = evaluate({"success": False, "output": None, "error": "Empty response", "steps": []}, skill_decision, state)
    assert not result.passed
    assert result.score == 0.0
    assert result.should_replan


def test_error_phrase_fails(state, skill_decision):
    result = evaluate(
        {"success": False, "output": None, "error": "I couldn't complete that action", "steps": []},
        skill_decision,
        state,
    )
    assert not result.passed


def test_traceback_fails(state, skill_decision):
    result = evaluate(
        {"success": False, "output": None, "error": "Traceback (most recent call last):", "steps": []},
        skill_decision,
        state,
    )
    assert not result.passed


def test_good_response_passes(state, skill_decision):
    result = evaluate(
        {"success": True, "output": "Opened Chrome successfully.", "error": None, "steps": []},
        skill_decision,
        state,
    )
    assert result.passed
    assert result.score >= 0.5


def test_retry_never_replans(state):
    decision = {"type": "skill", "name": "open_app", "_retry_attempt": True}
    result = evaluate({"success": False, "output": None, "error": "Browser timeout", "steps": []}, decision, state)
    assert not result.should_replan


def test_fast_chat_no_replan(state):
    result = evaluate(
        {"success": False, "output": None, "error": None, "steps": []},
        {"type": "fast_chat", "name": "respond"},
        state,
    )
    assert not result.should_replan
