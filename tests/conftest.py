from __future__ import annotations

from unittest.mock import patch

import pytest

from agent.state import State
from memory.core import Memory


@pytest.fixture
def state():
    return State(mode="fast")


@pytest.fixture
def memory(tmp_path):
    return Memory(base_dir=tmp_path / "memory")


@pytest.fixture
def mock_llm():
    with patch("models.llm.call_llm") as mock_call, patch("models.llm.call_llm_cached") as mock_cached:
        mock_call.return_value = '{"type":"chat","response":"test response"}'
        mock_cached.return_value = '{"type":"chat","response":"test response"}'
        yield mock_cached


@pytest.fixture
def registry():
    from skills.registry import SkillRegistry

    SkillRegistry._instance = None
    return SkillRegistry.instance()
