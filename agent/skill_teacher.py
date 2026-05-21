from __future__ import annotations

import json
import logging

from models.llm import call_llm_cached
from skills.learned import LearnedSkill, store_learned_skill
from skills.registry import SkillRegistry


logger = logging.getLogger("jarvis.skill_teacher")

TEACH_SYSTEM_PROMPT = """
You extract structured skill definitions from user instructions.
A skill is a named, repeatable sequence of atomic actions.
Atomic actions are: open_app, browse, type_text, search, click, system_command.

Return ONLY valid JSON in this exact format:
{
  "name": "skill_snake_case_name",
  "description": "one sentence description",
  "trigger_phrases": ["natural phrase users will say to run this skill"],
  "steps": [
    {"skill_name": "open_app", "params": {"app": "chrome"}},
    {"skill_name": "browse", "params": {"url": "{url}"}}
  ]
}

If the input is not a teachable skill, return: {"error": "not_a_skill"}
"""


def extract_skill_from_instruction(user_input: str) -> dict | None:
    """Use LLM to parse a user instruction into a structured skill definition."""
    response = call_llm_cached(
        "teach",
        TEACH_SYSTEM_PROMPT,
        user_input,
        temperature=0.1,
        max_tokens=500,
    )
    try:
        data = json.loads(response.strip())
        if "error" in data:
            return None
        return data
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON for skill extraction: %s", response)
        return None


def teach_skill(user_input: str, memory) -> str:
    """
    Called when user says 'teach you' or 'remember how to' or 'learn this'.
    Extracts skill, stores in memory, registers in registry.
    Returns confirmation string.
    """
    skill_def = extract_skill_from_instruction(user_input)
    if not skill_def:
        return "I couldn't understand that as a teachable skill. Try describing it step by step."

    store_learned_skill(
        memory=memory,
        name=skill_def["name"],
        description=skill_def["description"],
        steps=skill_def["steps"],
        trigger_phrases=skill_def.get("trigger_phrases", []),
    )

    registry = SkillRegistry.instance()
    registry.register_learned(
        LearnedSkill(
            name=skill_def["name"],
            description=skill_def["description"],
            steps=skill_def["steps"],
            trigger_phrases=skill_def.get("trigger_phrases", []),
        )
    )

    from agent.intent.learned_rules import register_learned_skill_rules

    register_learned_skill_rules(skill_def)
    logger.info("Gate rules registered for newly learned skill: %s", skill_def.get("name"))

    from agent.gate import get_gate
    from agent.gate_rule_generator import generate_rule_for_skill, save_rule_to_disk

    gate_rule = generate_rule_for_skill(
        skill_name=skill_def["name"],
        description=skill_def["description"],
        steps=skill_def["steps"],
    )
    if gate_rule:
        get_gate().add_rule(gate_rule)
        save_rule_to_disk(
            skill_name=skill_def["name"],
            description=skill_def["description"],
            steps=skill_def["steps"],
        )
        logger.info("Gate rule added and persisted for: %s", skill_def["name"])

    return f"Learned new skill: '{skill_def['name']}' — {skill_def['description']}"
