from __future__ import annotations

from agent.state import State
from skills.open_search_and_play import OpenSearchAndPlaySkill


def test_opens_youtube_search_and_falls_back_when_vision_unavailable(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "skills.automation.browser.actions.search_youtube_sync",
        lambda query: calls.append(("search", query)) or f"Searched YouTube for: {query}",
    )
    monkeypatch.setattr(
        "skills.automation.browser.actions.click_first_youtube_result_sync",
        lambda: calls.append(("click", None)) or "Clicked first YouTube result",
    )

    state = State(mode="fast")
    result = OpenSearchAndPlaySkill().run({"app": "youtube", "query": "telugu songs"}, state)

    assert result.success is True
    assert calls == [("search", "telugu songs"), ("click", None)]
    assert state.browser_url == "https://www.youtube.com/results?search_query=telugu+songs"
    assert state.active_app == "browser"
    assert result.output == "Searched YouTube for: telugu songs. Clicked first YouTube result"
