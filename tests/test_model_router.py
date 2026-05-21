from __future__ import annotations

import pytest

from agent.intent.schema import IntentName
from models import model_router


def test_model_router_defaults_to_qwen_and_gemma3_models():
    assert model_router._MAIN_MODEL == "qwen3:8b"
    assert model_router._ACTION_MODEL == "gemma3:4b"
    assert model_router._MAIN_MODEL_CHAIN == [
        "qwen3:8b",
        "qwen3:14b",
        "mistral:latest",
        "llama3.2:3b",
    ]
    assert model_router._ACTION_MODEL_CHAIN == [
        "gemma3:4b",
        "gemma2:2b",
        "qwen3:8b",
    ]


def test_model_router_exposes_model_roles():
    assert model_router.get_main_model() == "qwen3:8b"
    assert model_router.get_action_model() == "gemma3:4b"
    assert model_router.get_embed_model() == "nomic-embed-text"


def test_model_router_resolves_first_available_model_from_chain():
    available = ["llama3.2:3b", "qwen3:14b", "gemma3:4b"]

    assert model_router.resolve_best_model(model_router._MAIN_MODEL_CHAIN, available) == "qwen3:14b"
    assert model_router.resolve_best_model(["qwen3:8b", "gemma3:4b"], available) == "qwen3:14b"
    assert model_router.resolve_best_model(["missing:1b", "fallback:latest"], available) == "fallback:latest"


def test_action_model_availability_uses_gemma_check(monkeypatch):
    monkeypatch.setattr(model_router, "_check_gemma", lambda: True)

    assert model_router.is_action_model_available() is True


@pytest.mark.parametrize(
    "intent_name",
    [
        IntentName.OPEN_APP,
        IntentName.OPEN_AND_SEARCH,
        IntentName.OPEN_AND_TYPE,
        IntentName.OPEN_AND_PLAY,
        IntentName.WEB_BROWSE,
        IntentName.WEB_SEARCH,
        IntentName.GUI_CLICK,
        IntentName.GUI_TYPE,
        IntentName.FILE_SEARCH,
        IntentName.RUN_CODE,
    ],
)
def test_automation_intents_use_gemma_when_available(monkeypatch, intent_name):
    monkeypatch.setattr(model_router, "_check_gemma", lambda: True)

    assert model_router.get_model_for_intent(intent_name) == "gemma"


def test_automation_intents_fall_back_to_main_when_gemma_unavailable(monkeypatch):
    monkeypatch.setattr(model_router, "_check_gemma", lambda: False)

    assert model_router.get_model_for_intent(IntentName.OPEN_APP) == "main"


@pytest.mark.parametrize(
    "intent_name",
    [
        IntentName.CHAT,
        IntentName.WEB_SUMMARY,
        IntentName.LEARN_SKILL,
        IntentName.COMPOSE_EMAIL,
    ],
)
def test_reasoning_intents_use_main_without_gemma_check(monkeypatch, intent_name):
    def fail_check():
        raise AssertionError("main LLM intents should not check Gemma availability")

    monkeypatch.setattr(model_router, "_check_gemma", fail_check)

    assert model_router.get_model_for_intent(intent_name) == "main"
