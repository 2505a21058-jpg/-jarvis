from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.train_skill import LiveTrainSkill


@pytest.fixture
def skill():
    return LiveTrainSkill()


def test_returns_live_train_status(state, skill):
    with patch("skills._train_impl.get_live_train", return_value="Train ABC Express. Currently at Station X."):
        result = skill.execute({"train_number": "12345"}, state)
    assert result.success
    assert "12345" in result.output or "ABC" in result.output


def test_missing_train_number_returns_error(state, skill):
    result = skill.execute({}, state)
    assert not result.success


def test_missing_api_key_propagates(state, skill):
    with patch("skills._train_impl.get_live_train", return_value="RAPIDAPI_KEY is not configured"):
        result = skill.execute({"train_number": "12345"}, state)
    assert result.success
    assert "RAPIDAPI_KEY" in result.output
