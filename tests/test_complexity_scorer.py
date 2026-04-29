from __future__ import annotations

from agent.complexity_scorer import compute_complexity_score, should_use_fast_decide


def test_simple_not_escalated():
    assert not compute_complexity_score("what is Python?")["escalate"]


def test_greeting_not_escalated():
    assert should_use_fast_decide("hello how are you")


def test_teach_escalated():
    result = compute_complexity_score("teach you how to open my email")
    assert result["escalate"]
    assert result["reason"] == "hard_escalate_pattern"


def test_learn_how_to_escalated():
    assert compute_complexity_score("learn how to do this workflow")["escalate"]


def test_step_by_step_escalated():
    assert compute_complexity_score("explain step by step how to code this")["escalate"]


def test_multi_action_escalated():
    result = compute_complexity_score(
        "open chrome and search for python books and then download the first result"
    )
    assert result["escalate"]


def test_long_input_escalated():
    assert compute_complexity_score("hello " * 40)["escalate"]


def test_score_fields_present():
    result = compute_complexity_score("test input")
    for field in ("score", "token_count", "action_verbs", "clause_density", "escalate"):
        assert field in result


def test_empty_input():
    result = compute_complexity_score("")
    assert isinstance(result["escalate"], bool)
