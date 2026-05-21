"""
models/model_router.py

Decides which model handles a given intent.
Single source of truth for model assignment.

Rules:
- Automation tasks (PC, browser) -> Gemma (fast, local, no reasoning needed)
- Internet research -> Main LLM (needs synthesis and judgment)
- Chat, planning, teaching -> Main LLM
- If Gemma unavailable -> fall back to main LLM with warning
"""

import logging
import os

from agent.intent.schema import IntentName

logger = logging.getLogger("jarvis.model_router")

_MAIN_MODEL = os.getenv("JARVIS_MODEL", "qwen3:8b")
_ACTION_MODEL = os.getenv("JARVIS_ACTION_MODEL", "gemma3:4b")

_MAIN_MODEL_CHAIN = ["qwen3:8b", "qwen3:14b", "mistral:latest", "llama3.2:3b"]
_ACTION_MODEL_CHAIN = ["gemma3:4b", "gemma2:2b", "qwen3:8b"]

_MAIN_MODEL_FALLBACKS = _MAIN_MODEL_CHAIN
_ACTION_MODEL_FALLBACKS = _ACTION_MODEL_CHAIN

# Intents that should ALWAYS use Gemma when the local model is available.
GEMMA_INTENTS = {
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
    IntentName.SET_REMINDER,
}

# Intents that ALWAYS use the main LLM.
MAIN_LLM_INTENTS = {
    IntentName.CHAT,
    IntentName.WEB_SUMMARY,
    IntentName.LEARN_SKILL,
    IntentName.COMPOSE_EMAIL,
}

_gemma_available: bool | None = None


def _check_gemma() -> bool:
    global _gemma_available
    if _gemma_available is None:
        try:
            from models.gemma import is_available

            _gemma_available = is_available()
            if _gemma_available:
                logger.info("[MODEL ROUTER] Gemma available - automation tasks will use local model")
            else:
                logger.warning("[MODEL ROUTER] Gemma not available - automation tasks will use main LLM fallback")
        except Exception as exc:
            logger.warning("[MODEL ROUTER] Gemma availability check failed: %s", exc)
            _gemma_available = False
    return _gemma_available


def get_model_for_intent(intent_name: IntentName) -> str:
    """
    Returns "gemma" or "main" for a given intent.
    "gemma" means use models/gemma.py
    "main" means use models/llm.py call_llm()
    """
    try:
        normalized = IntentName(intent_name)
    except ValueError:
        return "main"

    if normalized in MAIN_LLM_INTENTS:
        return "main"

    if normalized in GEMMA_INTENTS and _check_gemma():
        return "gemma"

    return "main"


def get_main_model() -> str:
    """Return the active main model name."""
    return _MAIN_MODEL


def get_action_model() -> str:
    """Return the active action/automation model name."""
    return _ACTION_MODEL


def get_embed_model() -> str:
    """Return the embedding model name."""
    return os.getenv("JARVIS_EMBED_MODEL", "nomic-embed-text")


def is_action_model_available() -> bool:
    """Check if action model is available."""
    return _check_gemma()


def resolve_best_model(chain: list[str], available: list[str]) -> str:
    """
    Find first model from chain that is available.
    Matches by base name so qwen3:8b can use any pulled qwen3 variant.
    """
    available_base = [model.split(":")[0].lower() for model in available]
    for preferred in chain:
        base = preferred.split(":")[0].lower()
        if base in available_base:
            idx = available_base.index(base)
            return available[idx]
    return chain[-1]


def reset_availability_cache():
    """Force re-check of Gemma availability. Useful after ollama restart."""
    global _gemma_available
    _gemma_available = None
