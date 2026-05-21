from __future__ import annotations

from skills._weather_impl import API_KEY as W_API_KEY
from skills._weather_impl import get_weather
from skills._train_impl import RAPIDAPI_KEY as T_API_KEY
from skills._train_impl import check_pnr


def test_weather_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr("skills._weather_impl.API_KEY", "")

    result = get_weather("Hyderabad")

    assert "OPENWEATHER_API_KEY" in result


def test_train_lookup_reports_missing_rapidapi_key(monkeypatch):
    monkeypatch.setattr("skills._train_impl.RAPIDAPI_KEY", "")

    result = check_pnr("1234567890")

    assert "RAPIDAPI_KEY is not configured" in result
