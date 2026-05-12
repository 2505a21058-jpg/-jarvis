from __future__ import annotations

import pytest

from agent.gate import GATE_RULES, GateLayer, GateRule


@pytest.fixture
def gate():
    return GateLayer(rules=list(GATE_RULES))


def test_open_app(gate):
    result = gate.evaluate("open chrome")
    assert result.resolved
    assert result.skill_name == "open_app"
    assert result.params["app"] == "chrome"


def test_launch_alias(gate):
    result = gate.evaluate("launch firefox")
    assert result.resolved
    assert result.skill_name == "open_app"


def test_type_text(gate):
    result = gate.evaluate("type hello world")
    assert result.resolved
    assert result.skill_name == "type_text"
    assert result.params["text"] == "hello world"


def test_browse_url(gate):
    result = gate.evaluate("go to https://example.com")
    assert result.resolved
    assert result.skill_name == "browse"


def test_search(gate):
    result = gate.evaluate("search for python tutorials")
    assert result.resolved
    assert result.skill_name in {"browse", "search"}
    assert result.params["query"] == "python tutorials"


def test_set_env_var(gate):
    result = gate.evaluate("set JARVIS_VISION_VERIFY=true")
    assert result.resolved
    assert result.skill_name == "__set_env__"
    assert result.params["var"] == "JARVIS_VISION_VERIFY"
    assert result.params["val"] == "true"


def test_open_search_and_play_first_result(gate):
    result = gate.evaluate("open youtube, search telugu songs and play the first song")
    assert result.resolved
    assert result.skill_name == "open_search_and_play"
    assert result.params["app"] == "youtube"
    assert result.params["query"] == "telugu songs"


def test_open_search_then_action_falls_back_to_search(gate):
    result = gate.evaluate("open youtube, search telugu songs and like the first")
    assert result.resolved
    assert result.skill_name == "open_and_search"
    assert result.params["app"] == "youtube"
    assert result.params["query"] == "telugu songs"


def test_general_booking_routes_to_computer_control(gate):
    result = gate.evaluate("open chrome search for trains to hyderabad and book one")
    assert result.resolved
    assert result.skill_name == "computer_control"
    assert result.params["task"] == "open chrome search for trains to hyderabad and book one"


def test_paint_drawing_routes_to_computer_control(gate):
    result = gate.evaluate("draw a house in microsoft paint")
    assert result.resolved
    assert result.skill_name == "computer_control"
    assert result.params["task"] == "draw a house in microsoft paint"


def test_paint_drawing_save_routes_to_computer_control(gate):
    result = gate.evaluate("draw a house in microsoft paint and save as house.png")
    assert result.resolved
    assert result.skill_name == "computer_control"


def test_keyboard_control_routes_to_computer_control(gate):
    result = gate.evaluate("press ctrl s")
    assert result.resolved
    assert result.skill_name == "computer_control"
    assert result.params["task"] == "press ctrl s"


def test_form_fill_routes_to_computer_control(gate):
    result = gate.evaluate("fill the form with name as Shiva and email as test@example.com")
    assert result.resolved
    assert result.skill_name == "computer_control"


def test_cross_app_copy_routes_to_computer_control(gate):
    result = gate.evaluate("copy selected text from notepad to word")
    assert result.resolved
    assert result.skill_name == "computer_control"


def test_tab_management_routes_to_computer_control(gate):
    result = gate.evaluate("switch browser tab")
    assert result.resolved
    assert result.skill_name == "computer_control"


def test_disable_env_var_defaults_false(gate):
    result = gate.evaluate("disable jarvis_vision_verify")
    assert result.resolved
    assert result.skill_name == "__set_env__"
    assert result.params["var"] == "JARVIS_VISION_VERIFY"
    assert result.params["val"] == "false"


def test_greeting(gate):
    result = gate.evaluate("hello")
    assert result.resolved
    assert result.skill_name == "__direct_response__"


def test_thanks(gate):
    result = gate.evaluate("thanks")
    assert result.resolved
    assert result.skill_name == "__direct_response__"


def test_list_skills(gate):
    result = gate.evaluate("what can you do")
    assert result.resolved
    assert result.skill_name == "list_skills"


def test_unresolved_chat(gate):
    assert not gate.evaluate("what is machine learning?").resolved


def test_unresolved_complex(gate):
    assert not gate.evaluate("what is machine learning and open the first result").resolved


def test_empty_input(gate):
    assert not gate.evaluate("").resolved


def test_case_insensitive(gate):
    assert gate.evaluate("OPEN CHROME").resolved


def test_stats(gate):
    gate.evaluate("open chrome")
    gate.evaluate("what is AI?")
    stats = gate.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_dynamic_rule(gate):
    rule = GateRule(
        rule_id="test_rule",
        patterns=[r"do the test thing"],
        skill_name="test_skill",
        param_extractor=lambda match: {},
    )
    assert gate.add_rule(rule) is True
    assert gate.evaluate("do the test thing").resolved


def test_duplicate_rule_blocked(gate):
    rule = GateRule(
        rule_id="open_app",
        patterns=[r"test"],
        skill_name="test",
        param_extractor=lambda match: {},
    )
    assert gate.add_rule(rule) is False
