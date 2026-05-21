from __future__ import annotations

from agent.evaluate import evaluate


def test_empty_output_fails_and_recommends_retry():
    result = evaluate("", "open chrome", "open_app")

    assert result.success is False
    assert result.confidence == 0.0
    assert result.retry_recommended is True
    assert result.issues == ["Empty or null output"]
    assert result.source == "rule"


def test_error_phrase_gets_low_confidence():
    result = evaluate("Error: App not found: chrome", "open chrome", "open_app")

    assert result.success is False
    assert result.confidence == 0.1
    assert result.retry_recommended is True
    assert any("Hard failure pattern" in issue for issue in result.issues)


def test_timeout_indicator_gets_low_confidence():
    result = evaluate("The browser timed out after 10 seconds", "open chrome", "open_app")

    assert result.success is False
    assert result.confidence == 0.1
    assert result.retry_recommended is True


def test_good_skill_output_passes_with_high_confidence():
    result = evaluate("Chrome is now open.", "open chrome", "open_app")

    assert result.success is True
    assert result.confidence > 0.7
    assert result.retry_recommended is False


def test_hallucination_indicator_penalizes_non_chat():
    result = evaluate("I cannot browse the web from here.", "search current news", "web_summary")

    assert result.confidence <= 0.4
    assert any("Possible hallucination" in issue for issue in result.issues)


def test_hallucination_indicator_is_allowed_for_chat():
    result = evaluate("I cannot browse the web from here.", "what can you do?", "chat")

    assert "Possible hallucination" not in result.issues


def test_llm_not_called_by_default(monkeypatch):
    monkeypatch.setattr(
        "models.llm.call_llm_json",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("LLM evaluation should be opt-in")),
    )

    result = evaluate("This is a long enough answer to otherwise qualify for LLM quality checks.", "hello", "chat")

    assert result.source == "rule"


def test_llm_evaluation_skips_non_chat_even_when_requested(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "models.llm.call_llm_json",
        lambda **kwargs: calls.append(kwargs) or {"confidence": 0.1, "issues": ["bad"], "correction": ""},
    )

    result = evaluate(
        "Chrome opened successfully with a long enough response to otherwise qualify.",
        "open chrome",
        "open_app",
        use_llm=True,
    )

    assert result.source == "rule"
    assert calls == []


def test_optional_llm_evaluation_combines_conservatively(monkeypatch):
    monkeypatch.setattr(
        "models.llm.call_llm_json",
        lambda **kwargs: {
            "confidence": 0.3,
            "issues": ["Missed the question"],
            "correction": "Answer directly.",
        },
    )

    result = evaluate(
        "This is a long answer that passes rule checks but the evaluator should mark it weak.",
        "what did I ask?",
        "chat",
        use_llm=True,
    )

    assert result.success is False
    assert result.confidence == 0.3
    assert result.retry_recommended is True
    assert result.correction == "Answer directly."
    assert result.source == "combined"


def test_to_dict_preserves_legacy_keys():
    payload = evaluate("Chrome is now open.", "open chrome", "open_app").to_dict()

    assert payload["success"] is True
    assert payload["confidence"] > 0.7
    assert payload["passed"] is True
    assert payload["score"] == payload["confidence"]
    assert payload["quality_score"] == payload["confidence"]
    assert payload["retry_recommended"] is False
