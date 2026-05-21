from __future__ import annotations

from skills.automation import gemma_bridge


def test_plan_automation_returns_steps_from_gemma_json(monkeypatch):
    monkeypatch.setattr(
        gemma_bridge,
        "call_gemma_json",
        lambda prompt, system="", **kwargs: {
            "steps": [{"skill": "open_app", "params": {"app": "chrome"}}],
        },
    )

    assert gemma_bridge.plan_automation("open chrome") == [
        {"skill": "open_app", "params": {"app": "chrome"}}
    ]


def test_plan_automation_returns_empty_list_when_planning_fails(monkeypatch):
    def raise_error(prompt, system="", **kwargs):
        raise ValueError("bad json")

    monkeypatch.setattr(gemma_bridge, "call_gemma_json", raise_error)

    assert gemma_bridge.plan_automation("open chrome") == []
