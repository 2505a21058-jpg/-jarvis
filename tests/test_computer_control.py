from __future__ import annotations

from agent.state import State
from skills.computer_control import AutomationObservation, ComputerControlSkill, _build_plan


def test_builds_search_then_confirmation_for_booking():
    plan = _build_plan("open chrome search for trains to hyderabad and book one")

    assert plan[0].skill_name == "open_and_search"
    assert plan[0].params == {"app": "chrome", "query": "trains to hyderabad"}
    assert plan[-1].action == "user_confirmation"


def test_builds_paint_drawing_plan():
    plan = _build_plan("draw a house in microsoft paint")

    assert plan[0].skill_name == "open_app"
    assert plan[0].params == {"app": "paint"}
    assert plan[1].action == "draw"
    assert "house" in plan[1].params["subject"]


def test_builds_keyboard_plan_without_treating_key_as_button():
    plan = _build_plan("press ctrl s")

    assert len(plan) == 1
    assert plan[0].skill_name == "gui_automate"
    assert plan[0].params == {"action": "press", "keys": "ctrl+s"}


def test_execute_search_then_stops_before_booking(monkeypatch):
    calls = []
    notices = []

    def fake_execute_step(step, state, step_index):
        calls.append((step.skill_name, step.params, step_index))
        return True, "searched"

    monkeypatch.setattr("skills.computer_control._execute_skill_step", fake_execute_step)
    monkeypatch.setattr("skills.computer_control._notify_user", lambda message: notices.append(message))
    monkeypatch.setattr("skills.computer_control._observe", lambda context, step=None, force_vision=False: AutomationObservation())
    monkeypatch.setattr("skills.computer_control.time.sleep", lambda seconds: None)

    result = ComputerControlSkill().run(
        {"task": "open chrome search for trains to hyderabad and book one"},
        State(mode="fast"),
    )

    assert result.success is True
    assert calls == [("open_and_search", {"app": "chrome", "query": "trains to hyderabad"}, 0)]
    assert notices
    assert "will not complete bookings" in result.output


def test_builds_form_fill_plan_with_medium_risk():
    plan = _build_plan("fill the form with name as Shiva and email as test@example.com")

    assert len(plan) == 1
    assert plan[0].action == "fill_form"
    assert plan[0].risk == "medium"
    assert plan[0].params["fields"] == {"name": "Shiva", "email": "test@example.com"}


def test_builds_paint_save_export_plan():
    plan = _build_plan("draw a house in microsoft paint and save as house.png")

    assert [step.action for step in plan] == ["skill", "draw", "save_file"]
    assert plan[-1].risk == "medium"
    assert plan[-1].params["path"] == "house.png"


def test_builds_cross_app_copy_paste_plan():
    plan = _build_plan("copy selected text from notepad to word")

    assert [(step.skill_name, step.params) for step in plan] == [
        ("open_app", {"app": "notepad"}),
        ("gui_automate", {"action": "press", "keys": "ctrl+c"}),
        ("open_app", {"app": "word"}),
        ("gui_automate", {"action": "press", "keys": "ctrl+v"}),
    ]


def test_builds_tab_management_plan():
    plan = _build_plan("switch browser tab")

    assert len(plan) == 1
    assert plan[0].skill_name == "gui_automate"
    assert plan[0].params == {"action": "press", "keys": "ctrl+tab"}


def test_conditional_booking_handoff_records_condition(monkeypatch):
    notices = []
    monkeypatch.setattr("skills.computer_control._notify_user", lambda message: notices.append(message))
    monkeypatch.setattr("skills.computer_control._observe", lambda context, step=None, force_vision=False: AutomationObservation())
    monkeypatch.setattr("skills.computer_control.time.sleep", lambda seconds: None)

    result = ComputerControlSkill().run(
        {"task": "if the price is under 1000 book it"},
        State(mode="fast"),
    )

    assert result.success is True
    assert notices
    assert "condition is not safely verified" in result.output.lower()
    assert "will not complete bookings" in result.output


def test_strategy_chain_recovers_after_first_failure(monkeypatch):
    calls = []

    def fake_execute_step(step, state, step_index):
        calls.append(step.skill_name)
        if len(calls) == 1:
            return False, "primary failed"
        return True, "fallback worked"

    monkeypatch.setattr("skills.computer_control._execute_skill_step", fake_execute_step)
    monkeypatch.setattr("skills.computer_control._observe", lambda context, step=None, force_vision=False: AutomationObservation())
    monkeypatch.setattr("skills.computer_control.time.sleep", lambda seconds: None)

    result = ComputerControlSkill().run(
        {"task": "open chrome search for trains to hyderabad"},
        State(mode="fast"),
    )

    assert result.success is True
    assert len(calls) == 2
    assert "Recovered:" in result.output
