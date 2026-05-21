from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.train_skill import PNRSkill


@pytest.fixture
def skill():
    return PNRSkill()


def test_returns_formatted_pnr_status(state, skill):
    with patch("skills._train_impl.check_pnr", return_value="PNR 1234567890. Train ABC Express."):
        result = skill.execute({"pnr": "1234567890"}, state)
    assert result.success
    assert "1234567890" in result.output


def test_missing_pnr_returns_error(state, skill):
    result = skill.execute({}, state)
    assert not result.success


def test_missing_api_key_propagates(state, skill):
    with patch("skills._train_impl.check_pnr", return_value="RAPIDAPI_KEY is not configured"):
        result = skill.execute({"pnr": "1234567890"}, state)
    assert result.success
    assert "RAPIDAPI_KEY" in result.output
