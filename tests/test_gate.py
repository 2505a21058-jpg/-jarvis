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
