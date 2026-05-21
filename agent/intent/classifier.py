"""
agent/intent/classifier.py

Main entry point for intent classification.
Combines rule-based and LLM classifiers.
"""

import logging
import time

from agent.intent.llm_classifier import classify_with_llm
from agent.intent.rules import classify_with_rules
from agent.intent.schema import Intent

logger = logging.getLogger("jarvis.intent")

_stats = {
    "total": 0,
    "rule_hits": 0,
    "llm_hits": 0,
    "fallbacks": 0,
}


def classify(raw_input: str) -> Intent:
    start = time.monotonic()
    _stats["total"] += 1

    intent = classify_with_rules(raw_input)
    if intent is not None:
        _stats["rule_hits"] += 1
        logger.debug(
            "Intent classified by rule: %s (confidence=%.2f, entities=%s)",
            intent.name.value,
            intent.confidence,
            list(intent.entities.keys()),
        )
    else:
        _stats["llm_hits"] += 1
        intent = classify_with_llm(raw_input)
        if intent.classification_source == "fallback":
            _stats["fallbacks"] += 1
        logger.debug(
            "Intent classified by LLM: %s (confidence=%.2f)",
            intent.name.value,
            intent.confidence,
        )

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "[INTENT] %s | source=%s | confidence=%.2f | %.0fms",
        intent.name.value,
        intent.classification_source,
        intent.confidence,
        elapsed_ms,
    )
    return intent


def get_stats() -> dict:
    total = max(_stats["total"], 1)
    return {
        **_stats,
        "rule_hit_rate": _stats["rule_hits"] / total,
        "llm_hit_rate": _stats["llm_hits"] / total,
    }
