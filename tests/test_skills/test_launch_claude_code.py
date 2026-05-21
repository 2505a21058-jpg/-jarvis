from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.launch_claude_code import LaunchClaudeCodeSkill


@pytest.fixture
def skill():
    return LaunchClaudeCodeSkill()


def test_launches_editor_without_prompt(state, skill):
    with patch("shutil.which", return_value="C:\\Program Files\\cursor.exe"):
        with patch("subprocess.Popen") as mock_popen:
            result = skill.execute({}, state)
    assert result.success
    assert "Opened" in result.output
    mock_popen.assert_called_once()


def test_launches_with_prompt(state, skill):
    with patch("shutil.which", return_value="C:\\Program Files\\cursor.exe"):
        with patch("subprocess.Popen"):
            with patch("pyautogui.hotkey") as mock_hotkey:
                with patch("pyautogui.typewrite") as mock_type:
                    with patch("pyautogui.press") as mock_press:
                        with patch("pyperclip.copy"):
                            with patch("time.sleep"):
                                result = skill.execute({"prompt": "write tests"}, state)
    assert result.success
    assert "with prompt" in result.output
    mock_hotkey.assert_called()
    mock_type.assert_called_once_with("New Chat", interval=0.05)


def test_popen_failure_returns_error(state, skill):
    with patch("shutil.which", return_value="cursor"):
        with patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = skill.execute({}, state)
    assert not result.success


def test_no_editor_found_returns_error(state, skill):
    with patch("shutil.which", return_value=None):
        result = skill.execute({}, state)
    assert not result.success
    assert "No compatible editor" in result.error
