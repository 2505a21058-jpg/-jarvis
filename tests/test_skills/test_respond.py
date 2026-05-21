from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.respond import RespondSkill


@pytest.fixture
def skill():
    return RespondSkill()


def test_respond_calls_llm(state, skill):
    with patch("models.llm.call_llm", return_value="Hello! How can I help?") as mock_llm:
        result = skill.execute({"message": "hello"}, state)
    assert result.success
    assert result.output == "Hello! How can I help?"
    mock_llm.assert_called_once()


def test_respond_with_question(state, skill):
    with patch("models.llm.call_llm", return_value="Machine learning is...") as mock_llm:
        result = skill.execute({"message": "what is ML"}, state)
    assert result.success
    mock_llm.assert_called_once()


def test_respond_empty_message(state, skill):
    with patch("models.llm.call_llm", return_value="How can I help you?") as mock_llm:
        result = skill.execute({}, state)
    assert result.success


def test_respond_llm_failure_returns_error(state, skill):
    with patch("models.llm.call_llm", side_effect=RuntimeError("LLM down")):
        result = skill.execute({"message": "hello"}, state)
    assert not result.success
