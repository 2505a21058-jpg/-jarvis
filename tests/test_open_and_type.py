from __future__ import annotations

from agent.state import State
from skills.base import SkillResult
from skills.open_and_type import OpenAndTypeSkill


class StubRegistry:
    def __init__(self):
        self.calls = []

    def execute(self, name, params, state):
        self.calls.append((name, params, state))
        return SkillResult(success=True, output="search ok")


def test_web_app_redirects_to_search(monkeypatch):
    registry = StubRegistry()
    monkeypatch.setattr("skills.registry.SkillRegistry.instance", lambda: registry)

    state = State(mode="fast")
    result = OpenAndTypeSkill().run({"app": "google", "text": "hello"}, state)

    assert result.success is True
    assert registry.calls == [("open_and_search", {"app": "google", "query": "hello"}, state)]
    assert "used search instead of typing" in result.output
