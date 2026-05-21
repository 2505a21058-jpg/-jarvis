"""
agent/intent/learned_rules.py

Dynamically generated intent rules from learned skills.
Called at startup and when a new skill is learned.
"""

from __future__ import annotations

import logging

from agent.intent.schema import Entity, Intent, IntentName


logger = logging.getLogger("jarvis.intent.learned_rules")

# Maps trigger_phrase (normalized) -> (skill_name, params)
_LEARNED_RULES: dict[str, tuple[str, dict]] = {}


def _normalize_phrase(text: str) -> str:
    return str(text or "").lower().strip().rstrip(".,!?")


def register_learned_skill_rules(skill_def: dict) -> int:
    """
    Register gate rules for a learned skill.
    Returns number of rules registered.
    """
    from skills.learned import extract_trigger_phrases

    skill_name = str(skill_def.get("name", "") or "").strip()
    if not skill_name:
        return 0

    count = 0
    for phrase in extract_trigger_phrases(skill_def):
        normalized = _normalize_phrase(phrase)
        if not normalized:
            continue
        _LEARNED_RULES[normalized] = (skill_name, {})
        logger.debug("[LEARNED RULES] '%s' -> %s", normalized, skill_name)
        count += 1

    if count:
        logger.info("[LEARNED RULES] Registered %s gate rules for skill: %s", count, skill_name)
    return count


def load_all_learned_rules(memory=None) -> int:
    """
    Load gate rules for all learned skills at startup.
    Returns total rules registered.
    """
    try:
        from skills.learned import get_all_learned_skills

        skills = get_all_learned_skills(memory)
        total = 0
        for skill_def in skills:
            total += register_learned_skill_rules(skill_def)
        logger.info("[LEARNED RULES] Loaded %s rules from %s learned skills", total, len(skills))
        return total
    except Exception as exc:
        logger.warning("[LEARNED RULES] Failed to load learned rules: %s", exc)
        return 0


def classify_with_learned_rules(raw_input: str) -> Intent | None:
    """
    Check if input matches any learned skill trigger phrase.
    Returns Intent or None.
    """
    if not _LEARNED_RULES:
        return None

    normalized = _normalize_phrase(raw_input)

    if normalized in _LEARNED_RULES:
        skill_name, _params = _LEARNED_RULES[normalized]
        return Intent(
            name=IntentName.UNKNOWN,
            entities={
                "__learned_skill__": Entity(
                    name="__learned_skill__",
                    value=skill_name,
                )
            },
            confidence=1.0,
            raw_input=raw_input,
            classification_source="learned_rule",
        )

    for phrase, (skill_name, _params) in _LEARNED_RULES.items():
        if normalized.startswith(phrase):
            return Intent(
                name=IntentName.UNKNOWN,
                entities={
                    "__learned_skill__": Entity(
                        name="__learned_skill__",
                        value=skill_name,
                    )
                },
                confidence=0.9,
                raw_input=raw_input,
                classification_source="learned_rule_prefix",
            )

    return None
