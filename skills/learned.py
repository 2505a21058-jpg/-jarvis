from __future__ import annotations

import json
import logging
from typing import Any

from skills.base import SkillBase, SkillResult
from skills.registry import SkillRegistry


logger = logging.getLogger("jarvis.skills.learned")


class LearnedSkill(SkillBase):
    """A dynamically created skill from user-taught action sequences."""

    def __init__(self, name: str, description: str, steps: list[dict]):
        self.name = name
        self.description = description
        self.steps = steps

    def execute(self, params: dict, state) -> SkillResult:
        """
        Execute a composite learned skill.

        Physical workflows run through the skill registry. Computation-style
        skills delegate to the LLM so they do not accidentally type into UI.
        """
        from skills.registry import SkillRegistry

        physical_skills = {
            "open_app",
            "browse",
            "type_text",
            "search",
            "system_command",
            "send_email",
            "read_report",
            "launch_claude_code",
            "system_search",
            "click_element",
        }

        registry = SkillRegistry.instance()
        outputs = []
        all_physical = all(
            step.get("skill_name", "") in physical_skills
            for step in self.steps
        )

        if not all_physical or self._looks_like_computation_skill():
            return self._execute_via_llm(params)

        context = dict(params or {})
        for step in self.steps:
            skill_name = step["skill_name"]
            raw_params = step.get("params", {})
            resolved = {}
            for key, value in raw_params.items():
                if isinstance(value, str):
                    try:
                        resolved[key] = value.format(**context)
                    except KeyError:
                        resolved[key] = value
                else:
                    resolved[key] = value

            result = registry.execute(skill_name, resolved, state)
            if not result.success:
                return SkillResult(
                    success=False,
                    output=None,
                    error=f"Step '{skill_name}' failed: {result.error}",
                    skill_name=self.name,
                )
            if result.output:
                outputs.append(str(result.output))
                context[f"step_{self.steps.index(step)}_output"] = result.output

        return SkillResult(
            success=True,
            output="\n".join(outputs) if outputs else f"Completed {self.name}",
            skill_name=self.name,
        )

    def _looks_like_computation_skill(self) -> bool:
        text = " ".join(
            [
                str(self.name or ""),
                str(self.description or ""),
                " ".join(
                    str(step.get("description") or step.get("skill_name") or "")
                    for step in self.steps
                ),
            ]
        ).lower()
        computation_markers = {
            "reverse",
            "calculate",
            "compute",
            "math",
            "convert",
            "summarize text",
            "translate",
            "analyze",
            "classify",
            "extract",
            "format",
            "rewrite",
            "generate",
        }
        return any(marker in text for marker in computation_markers)

    def _execute_via_llm(self, params: dict) -> SkillResult:
        """Execute skill logic via LLM for non-physical/computation skills."""
        try:
            from models.llm import call_llm

            steps_description = "\n".join(
                f"- {step.get('description', step.get('skill_name', ''))}"
                for step in self.steps
            )
            param_str = str(params) if params else "no additional params"

            response = call_llm(
                system=(
                    f"You are executing the skill '{self.name}': {self.description}\n"
                    f"Steps:\n{steps_description}\n"
                    "Complete the task and respond with just the result."
                ),
                user=f"Execute with params: {param_str}",
                temperature=0.1,
                max_tokens=200,
            )
            return SkillResult(success=True, output=response.strip(), skill_name=self.name)
        except Exception as exc:
            return SkillResult(
                success=False,
                output=None,
                error=f"LLM execution failed: {exc}",
                skill_name=self.name,
            )


def store_learned_skill(memory, name: str, description: str, steps: list[dict]) -> None:
    """Persist a learned skill using the current Memory API."""
    payload = {
        "type": "learned_skill",
        "name": name,
        "description": description,
        "steps": steps,
    }
    memory.store(
        {
            "type": "learned_skill",
            "skill_name": name,
            "content": json.dumps(payload, ensure_ascii=False),
        }
    )
    logger.info("Stored learned skill: %s", name)


def _memory_records(memory) -> list[dict[str, Any]]:
    reader = getattr(memory, "_read_jsonl", None)
    memory_path = getattr(memory, "memory_path", None)
    if callable(reader) and memory_path is not None:
        try:
            return reader(memory_path)
        except Exception as exc:
            logger.warning("Failed to read learned skills from memory store: %s", exc)

    fallback = memory.retrieve("learned_skill", mode="nerd")
    if isinstance(fallback, dict):
        matches = fallback.get("matches")
        if isinstance(matches, list):
            return matches
    return []


def load_learned_skills(memory) -> list[LearnedSkill]:
    """Load all learned skills from memory and return as LearnedSkill instances."""
    skills = []
    for record in _memory_records(memory):
        if not isinstance(record, dict):
            continue
        if str(record.get("type", "")).strip().lower() != "learned_skill":
            continue

        try:
            data = json.loads(str(record.get("content", "")).strip())
            if data.get("type") == "learned_skill" or "steps" in data:
                skills.append(
                    LearnedSkill(
                        name=data["name"],
                        description=data["description"],
                        steps=data["steps"],
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to load learned skill entry: %s", exc)
    return skills


def register_learned_skills(memory) -> None:
    """Load and register all persisted learned skills into the registry."""
    registry = SkillRegistry.instance()
    for skill in load_learned_skills(memory):
        registry.register_learned(skill)
        logger.info("Re-registered learned skill: %s", skill.name)
