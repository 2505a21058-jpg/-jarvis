"""
agent/gate_rule_generator.py
Generates and persists GateRule objects from learned skill definitions.
"""

from __future__ import annotations

import json
import logging
import os
import re

from agent.gate import GateRule


logger = logging.getLogger("jarvis.gate_rule_generator")

GATE_RULES_PATH = "memory/gate_rules.jsonl"

GENERIC_WORDS = {"do", "run", "use", "execute", "start", "open", "go", "the"}


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", str(text or "").lower()).strip()


def generate_rule_for_skill(skill_name: str, description: str, steps: list) -> GateRule | None:
    _ = steps
    name_words = _normalize(skill_name).replace("_", " ").split()

    if len(name_words) < 1:
        return None

    if set(name_words).issubset(GENERIC_WORDS):
        logger.warning("Skill name too generic for gate rule: %s", skill_name)
        return None

    common_phrases = {
        "remember",
        "save",
        "store",
        "keep",
        "note",
        "learn",
        "show",
        "tell",
        "give",
        "make",
        "do",
        "get",
        "set",
    }
    if len(name_words) == 1 and name_words[0] in common_phrases:
        logger.warning("Skill name is a common verb, skipping gate rule: %s", skill_name)
        return None

    name_phrase = " ".join(name_words)
    patterns = [
        rf"(?:run|use|execute|do|start|apply)\s+{re.escape(name_phrase)}\s*(?:now|please|for me)?",
        rf"{re.escape(name_phrase)}\s*(?:now|please|for me)?",
    ]

    desc_words = _normalize(description).split()
    if len(desc_words) >= 4:
        desc_phrase = " ".join(desc_words[:4])
        if not any(word in desc_words[:4] for word in {"remember", "store", "save", "learn"}):
            patterns.append(rf"{re.escape(desc_phrase)}.*")

    return GateRule(
        rule_id=f"learned_{skill_name}",
        patterns=patterns,
        skill_name=skill_name,
        param_extractor=lambda match: {},
        description=f"Auto-generated rule for learned skill: {skill_name}",
    )


def save_rule_to_disk(skill_name: str, description: str, steps: list) -> None:
    os.makedirs(os.path.dirname(GATE_RULES_PATH), exist_ok=True)
    entry = {"skill_name": skill_name, "description": description, "steps": steps}
    with open(GATE_RULES_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.debug("Persisted gate rule definition: %s", skill_name)


def load_rules_from_disk() -> list[GateRule]:
    rules = []
    if not os.path.exists(GATE_RULES_PATH):
        return rules
    with open(GATE_RULES_PATH, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                rule = generate_rule_for_skill(
                    entry["skill_name"],
                    entry.get("description", ""),
                    entry.get("steps", []),
                )
                if rule:
                    rules.append(rule)
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning("Failed to reload gate rule: %s", exc)
    logger.info("Loaded %s learned skill gate rules from disk", len(rules))
    return rules
