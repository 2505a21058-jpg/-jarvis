from __future__ import annotations

from agent.planner import PLANNER_SYSTEM, _validate_plan


def test_planner_allows_open_search_and_play():
    plan_data = {
        "goal": "open youtube, search telugu songs and play the first song",
        "steps": [
            {
                "index": 0,
                "skill_name": "open_search_and_play",
                "description": "Search YouTube and open the first result",
                "params": {"app": "youtube", "query": "telugu songs"},
                "depends_on": [],
                "output_key": "youtube_result",
            }
        ],
    }

    valid, reason = _validate_plan(plan_data)
    assert valid is True
    assert reason == ""


def test_planner_prompt_mentions_youtube_guardrails():
    assert "open_search_and_play" in PLANNER_SYSTEM
    assert 'NEVER open "notepad"' in PLANNER_SYSTEM
    assert 'app="youtube"' in PLANNER_SYSTEM


def test_planner_allows_computer_control():
    plan_data = {
        "goal": "open chrome search for trains to hyderabad and book one",
        "steps": [
            {
                "index": 0,
                "skill_name": "computer_control",
                "description": "Use general computer control for the full workflow",
                "params": {"task": "open chrome search for trains to hyderabad and book one"},
                "depends_on": [],
                "output_key": "automation_result",
            }
        ],
    }

    valid, reason = _validate_plan(plan_data)
    assert valid is True
    assert reason == ""


def test_planner_prompt_mentions_general_ui_workflows():
    assert "computer_control" in PLANNER_SYSTEM
    assert "drawing" in PLANNER_SYSTEM
    assert "bookings" in PLANNER_SYSTEM
