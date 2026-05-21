from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from skills.run_code import RunCodeSkill


@pytest.fixture
def skill():
    return RunCodeSkill()


def test_executes_generated_code(state, skill):
    with patch("models.llm.call_llm", return_value="print('hello')"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hello\n"
            result = skill.execute({"task": "print hello"}, state)
    assert result.success


def test_executes_raw_code(state, skill):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "42\n"
        with patch("models.llm.call_llm") as mock_llm:
            result = skill.execute({"code": "print(42)"}, state)
    assert result.success
    mock_llm.assert_not_called()


def test_blocks_dangerous_system_call(state, skill):
    result = skill.execute({"code": "os.system('rm -rf /')"}, state)
    assert not result.success
    assert "blocked" in result.error.lower()


def test_blocks_dangerous_subprocess(state, skill):
    result = skill.execute({"code": "subprocess.run(['rm', '-rf', '/'])"}, state)
    assert not result.success
    assert "blocked" in result.error.lower()


def test_missing_task_and_code_returns_error(state, skill):
    result = skill.execute({}, state)
    assert not result.success


def test_code_timeout_is_handled(state, skill):
    with patch("subprocess.run", side_effect=TimeoutExpired("cmd", 10)):
        result = skill.execute({"code": "print('hi')"}, state)
    assert not result.success


class TimeoutExpired(subprocess.TimeoutExpired):

    def __init__(self, cmd, timeout=10):
        super().__init__(cmd, timeout)
