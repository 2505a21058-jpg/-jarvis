from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from skills.gui_automate import GUIAutomateSkill


@pytest.fixture
def skill():
    return GUIAutomateSkill()


def test_click_action(state, skill):
    with patch("skills.gui_automate._find_and_click", return_value=(True, "Clicked 'OK'")):
        result = skill.execute({"action": "click", "element": "OK"}, state)
    assert result.success


def test_type_active(state, skill):
    with patch("skills.gui_automate._type_active", return_value=(True, "Typed 5 characters")):
        result = skill.execute({"action": "type_active", "text": "hello"}, state)
    assert result.success


def test_press_hotkey(state, skill):
    with patch("skills.gui_automate._press_key_sequence", return_value=(True, "Pressed ctrl+s")):
        result = skill.execute({"action": "press", "keys": "ctrl+s"}, state)
    assert result.success


def test_get_active_window(state, skill):
    with patch("skills.gui_automate._get_active_window_title", return_value="Notepad"):
        result = skill.execute({"action": "get_active_window"}, state)
    assert result.success


def test_unknown_action_returns_error(state, skill):
    result = skill.execute({"action": "invalid"}, state)
    assert not result.success
