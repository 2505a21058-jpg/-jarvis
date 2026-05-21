from __future__ import annotations

from skills import SkillBase, SkillResult


class WeatherSkill(SkillBase):
    name = "weather"
    description = "Get current weather for a city"
    timeout_seconds = 10.0

    def execute(self, params: dict, state) -> SkillResult:
        from skills._weather_impl import get_weather

        city = str(params.get("city") or params.get("query") or "Hyderabad").strip()
        result = get_weather(city)
        return SkillResult(success=result is not None, output=result, skill_name=self.name)
