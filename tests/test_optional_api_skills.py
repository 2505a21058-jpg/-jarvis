from __future__ import annotations

from skills import train, weather, web_search


def test_weather_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(weather, "API_KEY", "")

    result = weather.get_weather("Hyderabad")

    assert "OPENWEATHER_API_KEY" in result


def test_web_search_weather_reports_missing_api_key(monkeypatch):
    monkeypatch.setattr(web_search, "API_KEY", "")

    result = web_search.get_weather("Hyderabad")

    assert "OPENWEATHER_API_KEY" in result


def test_train_lookup_reports_missing_rapidapi_key(monkeypatch):
    monkeypatch.setattr(train, "RAPIDAPI_KEY", "")

    result = train.check_pnr("1234567890")

    assert "RAPIDAPI_KEY is not configured" in result
