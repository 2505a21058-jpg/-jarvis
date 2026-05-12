from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any


EXPERIENCES_PATH = Path("memory") / "experiences.jsonl"
EXPERIENCE_MAX_BYTES = 5 * 1024 * 1024
logger = logging.getLogger("jarvis.learn")

_TRIVIAL_RESPONSES = {
    "hello! how can i help you today?",
    "you're welcome!",
    "plan completed successfully.",
    "available skills:",
    "hi! how can i help?",
    "how can i help you today?",
    "later.",
    "4",
}

_TRIVIAL_INPUTS = {
    # Greetings
    "hi", "hello", "hey", "howdy", "sup", "whatsup", "wassup",
    "hi there", "hey there", "hello there",

    # Acknowledgements
    "thanks", "thank you", "thx", "ty", "cheers", "np", "no problem",
    "ok", "okay", "k", "kk", "got it", "understood", "sure", "yep",
    "yup", "yeah", "yes", "no", "nope", "nah",

    # Slang for nothing / casual
    "ntg", "ntn", "nothing", "nothin", "nada", "nm", "not much",
    "nmh", "nthing", "nothing much",

    # Farewells
    "bye", "goodbye", "later", "cya", "see ya", "good night",
    "gn", "ttyl", "brb",

    # Reactions
    "lol", "haha", "hehe", "wow", "nice", "cool", "great",
    "awesome", "perfect", "good", "bad", "ok cool", "ah",
    "oh", "hmm", "faaaah", "ugh",

    # Quit
    "quit", "exit",
}

_MIN_INPUT_LENGTH = 15
_MIN_RESPONSE_LENGTH = 30
_STORE_THRESHOLD = 0.45
_PROMOTION_THRESHOLD = 0.85


def _compute_importance(user_input: str, response: str, decision: dict) -> float:
    score = 0.5
    decision_type = decision.get("type", "")

    if decision_type == "teach_skill":
        return 1.0

    if decision_type in ("skill", "plan"):
        score += 0.25

    if len(response) > 300:
        score += 0.15
    elif len(response) > 150:
        score += 0.08

    if "?" in user_input and len(user_input) > 20:
        score += 0.08

    if any(word in response.lower() for word in ("failed", "error", "couldn't", "unable")):
        score += 0.10

    if len(user_input) < _MIN_INPUT_LENGTH:
        score -= 0.25
    if len(response) < _MIN_RESPONSE_LENGTH:
        score -= 0.20

    if decision_type == "fast_chat" and len(response) < 80:
        score -= 0.15

    return max(0.0, min(1.0, score))


def _is_trivial(user_input: str, response: str) -> bool:
    """Fast check: is this exchange too trivial to store at all?"""
    try:
        from memory.personal_facts import extract_fact

        if extract_fact(user_input):
            logger.debug("learn(): personal fact detected - skipping trivial check")
            return False
    except Exception as exc:
        # Fact extraction failures are logged so learning skips are diagnosable.
        logger.debug("Personal fact trivial-check skipped: %s", exc)

    input_normalized = user_input.strip().lower().rstrip("?!.")
    response_normalized = response.strip().lower()

    if input_normalized in _TRIVIAL_INPUTS:
        return True
    if response_normalized in _TRIVIAL_RESPONSES:
        return True
    if any(response_normalized.startswith(item) for item in _TRIVIAL_RESPONSES if item.endswith(":")):
        return True
    if len(user_input.strip()) < 3:
        return True
    return False


def _is_duplicate(content: str, memory) -> bool:
    """Check if near-identical content was recently stored."""
    fingerprint = content[:60].lower().strip()
    try:
        recent = memory.recent(n=15)
        for entry in recent:
            stored = entry.get("content", "")[:60].lower().strip()
            if stored == fingerprint:
                return True
    except Exception as exc:
        # Duplicate detection failures are logged while preserving the existing store path.
        logger.debug("Duplicate experience check skipped: %s", exc)
    return False


def _extract_fields(
    observation: Any,
    decision: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> tuple[str, str, dict[str, Any]]:
    decision = decision or {}
    observation = observation or {}
    result = result or {}

    user_input = (
        str(observation.get("input", ""))
        if isinstance(observation, dict)
        else str(observation or "")
    )
    response = (
        str(result.get("output", ""))
        if isinstance(result, dict)
        else str(result or "")
    )
    return user_input, response, decision


def learn(
    observation: Any,
    decision: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    evaluation: dict[str, Any] | None = None,
    memory: Any = None,
) -> dict[str, Any] | None:
    """
    Selectively record an experience to memory.
    Only stores exchanges that are genuinely worth remembering.
    """
    _ = evaluation
    user_input, response, decision = _extract_fields(observation, decision, result)

    personal_fact = None
    try:
        from memory.personal_facts import extract_fact, store_fact

        personal_fact = extract_fact(user_input)
        if personal_fact:
            store_fact(user_input)
    except Exception as exc:
        logger.debug("Personal fact learning skipped: %s", exc)
        personal_fact = None

    if not personal_fact and _is_trivial(user_input, response):
        logger.debug("learn(): skipping trivial exchange")
        return None

    importance = _compute_importance(user_input, response, decision)
    if personal_fact:
        importance = max(importance, 0.9)

    if importance < _STORE_THRESHOLD:
        logger.debug("learn(): skipping low-importance exchange (score=%.2f)", importance)
        return None

    experience = {
        "user_input": user_input[:300],
        "response": response[:500],
        "decision_type": decision.get("type", "unknown"),
        "skill_name": decision.get("name", ""),
        "importance": importance,
        "timestamp": time.time(),
    }

    content = json.dumps(experience, ensure_ascii=True)

    if memory is not None and _is_duplicate(content, memory):
        logger.debug("learn(): skipping duplicate experience")
        return None

    tags = ["experience", decision.get("type", "unknown"), decision.get("name", "")]

    if memory is not None and hasattr(memory, "store_experience"):
        memory.store_experience(content=content, tags=tags)
        logger.debug("learn(): stored experience (importance=%.2f)", importance)

        if importance >= _PROMOTION_THRESHOLD:
            long_term_entry = {
                "content": content,
                "tags": ["experience", "long_term_promotion"],
                "metadata": {"importance": importance, "source": "auto_promotion"},
                "timestamp": time.time(),
            }
            try:
                memory.promote_to_long_term(long_term_entry)
            except Exception as exc:
                logger.warning("Long-term promotion failed (non-critical): %s", exc)
    else:
        EXPERIENCES_PATH.parent.mkdir(exist_ok=True)
        with open(EXPERIENCES_PATH, "a", encoding="utf-8") as handle:
            handle.write(content + "\n")

    if (
        memory is not None
        and hasattr(memory, "prune_experiences")
        and os.path.exists(EXPERIENCES_PATH)
        and os.path.getsize(EXPERIENCES_PATH) > EXPERIENCE_MAX_BYTES
    ):
        memory.prune_experiences(max_entries=700)
        logger.info("Pruned experience memory (exceeded 5MB)")

    return experience
