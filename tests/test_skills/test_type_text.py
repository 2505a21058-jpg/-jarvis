from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.type_text import TypeTextSkill


class _FakeState:
    active_app = "notepad"
    active_platform = "windows"
    last_action = ""


@pytest.fixture
def state():
    return _FakeState()


def test_types_text_into_active_window(state):
    skill = TypeTextSkill()
    with patch("skills.type_text.focus_app", return_value=True):
        with patch("pyautogui.write") as mock_write:
            result = skill.execute({"text": "hello world"}, state)
    assert result.success
    mock_write.assert_called_once()


def test_empty_text_returns_error(state):
    skill = TypeTextSkill()
    result = skill.execute({"text": ""}, state)
    assert not result.success


def test_missing_state_active_app_returns_error():
    skill = TypeTextSkill()
    result = skill.execute({"text": "hello"}, {})
    assert not result.success


def test_focus_failure_raises_error(state):
    skill = TypeTextSkill()
    with patch("skills.type_text.focus_app", return_value=False):
        result = skill.execute({"text": "hello"}, state)
    assert not result.success
    assert "Could not focus" in result.error


def test_long_text_returns_error(state):
    skill = TypeTextSkill()
    result = skill.execute({"text": "x" * 1001}, state)
    assert not result.success
