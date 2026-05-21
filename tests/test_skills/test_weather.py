from __future__ import annotations

from unittest.mock import patch

import pytest

from skills.weather_skill import WeatherSkill


@pytest.fixture
def skill():
    return WeatherSkill()


def test_returns_formatted_weather(state, skill):
    with patch("skills._weather_impl.get_weather", return_value="Hyderabad: clear sky, 30°C"):
        result = skill.execute({"city": "Hyderabad"}, state)
    assert result.success
    assert "Hyderabad" in result.output
    assert "30°C" in result.output


def test_defaults_to_hyderabad(state, skill):
    with patch("skills._weather_impl.get_weather", return_value="Hyderabad: clear sky, 30°C") as mock:
        result = skill.execute({}, state)
    assert result.success
    mock.assert_called_with("Hyderabad")


def test_missing_api_key_propagates_message(state, skill):
    with patch("skills._weather_impl.get_weather", return_value="Weather API key is not configured"):
        result = skill.execute({"city": "London"}, state)
    assert result.success
    assert "API key" in result.output
