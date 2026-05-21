from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.reminder import ReminderSkill


@pytest.fixture
def skill():
    return ReminderSkill()


def test_sets_relative_reminder(state, skill):
    with patch("threading.Timer") as mock_timer:
        result = skill.execute({"message": "check code", "delay": "5 minutes"}, state)
    assert result.success
    mock_timer.assert_called_once()
    kwargs = mock_timer.call_args[1]
    assert 290 <= kwargs["interval"] <= 310


def test_sets_alarm(state, skill):
    with patch("threading.Timer") as mock_timer:
        result = skill.execute({"message": "Alarm", "delay": "10 seconds", "is_alarm": True}, state)
    assert result.success
    assert "Alarm" in result.output


def test_sets_using_task_fallback(state, skill):
    with patch("threading.Timer"):
        result = skill.execute({"task": "call mom", "delay": "5 minutes"}, state)
    assert result.success
    assert "call mom" in result.output


def test_invalid_delay_defaults(state, skill):
    with patch("threading.Timer") as mock_timer:
        result = skill.execute({"message": "test", "delay": "not a time"}, state)
    assert result.success
    kwargs = mock_timer.call_args[1]
    assert kwargs["interval"] == 300.0  # default 5 min
