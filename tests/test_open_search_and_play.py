from __future__ import annotations

from agent.state import State
from skills.open_search_and_play import OpenSearchAndPlaySkill


def test_opens_youtube_search_and_falls_back_when_vision_unavailable(monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    monkeypatch.setattr("agent.screen_verify._take_screenshot", lambda: None)

    state = State(mode="fast")
    result = OpenSearchAndPlaySkill().run({"app": "youtube", "query": "telugu songs"}, state)

    assert result.success is True
    assert opened == ["https://www.youtube.com/results?search_query=telugu+songs"]
    assert state.browser_url == opened[0]
    assert state.active_app == "browser"
    assert "click the first result to play it" in result.output
