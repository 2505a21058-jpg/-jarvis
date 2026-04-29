"""
skills/registry.py

Versioned skill registry for Jarvis.
Rules:
  - Built-in skills (source="builtin") cannot be overridden by learned skills
  - Learned skills (source="learned") can override other learned skills with the same name
  - All registrations are logged with source and version
  - list_skills() includes source and version metadata
"""

import logging
from typing import Any, Optional

from skills.base import SkillBase, SkillResult


logger = logging.getLogger("jarvis.skills.registry")


class SkillEntry:
    def __init__(self, skill: SkillBase, source: str = "builtin", version: int = 1):
        self.skill = skill
        self.source = source
        self.version = version
        self.call_count = 0
        self.error_count = 0

    def __repr__(self):
        return f"SkillEntry(name={self.skill.name}, source={self.source}, v={self.version})"


class SkillRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: dict[str, SkillEntry] = {}
        return cls._instance

    def register(self, skill: SkillBase, source: str = "builtin") -> bool:
        """
        Register a skill.
        Returns True on success, False if registration was blocked.
        Built-in skills cannot be overridden by non-builtin sources.
        """
        if not skill.name:
            raise ValueError(f"Skill {type(skill).__name__} has no name set")

        existing = self._skills.get(skill.name)
        if existing:
            if existing.source == "builtin" and source != "builtin":
                logger.warning(
                    "Blocked attempt to override built-in skill '%s' from source '%s'",
                    skill.name,
                    source,
                )
                return False
            new_version = existing.version + 1
            logger.info(
                "Overriding skill '%s' (source: %s -> %s, v%s -> v%s)",
                skill.name,
                existing.source,
                source,
                existing.version,
                new_version,
            )
            self._skills[skill.name] = SkillEntry(skill, source=source, version=new_version)
        else:
            logger.info("Registered skill: '%s' [source=%s]", skill.name, source)
            self._skills[skill.name] = SkillEntry(skill, source=source, version=1)

        return True

    def register_builtin(self, skill: SkillBase) -> bool:
        """Convenience method for built-in skill registration."""
        return self.register(skill, source="builtin")

    def register_learned(self, skill: SkillBase) -> bool:
        """Convenience method for learned skill registration (can override other learned)."""
        return self.register(skill, source="learned")

    def get(self, name: str) -> Optional[SkillBase]:
        entry = self._skills.get(name)
        return entry.skill if entry else None

    def get_entry(self, name: str) -> Optional[SkillEntry]:
        return self._skills.get(name)

    def execute(self, name: str, params: dict, state: Any) -> SkillResult:
        entry = self._skills.get(name)
        if not entry:
            logger.warning("Unknown skill requested: '%s'", name)
            return SkillResult(
                success=False,
                output=None,
                error=f"Unknown skill: '{name}'. Use 'list skills' to see available skills.",
                skill_name=name,
            )
        entry.call_count += 1
        result = entry.skill.run(params, state)
        if not result.success:
            entry.error_count += 1
        return result

    def list_skills(self) -> list[dict]:
        return [
            {
                "name": entry.skill.name,
                "description": entry.skill.description,
                "source": entry.source,
                "version": entry.version,
                "call_count": entry.call_count,
                "error_count": entry.error_count,
            }
            for entry in self._skills.values()
        ]

    def remove(self, name: str, allow_builtin: bool = False) -> bool:
        """Remove a skill by name. Built-ins require explicit allow_builtin=True."""
        entry = self._skills.get(name)
        if not entry:
            return False
        if entry.source == "builtin" and not allow_builtin:
            logger.warning("Refused to remove built-in skill: '%s'", name)
            return False
        del self._skills[name]
        logger.info("Removed skill: '%s'", name)
        return True

    def stats(self) -> dict:
        return {
            "total": len(self._skills),
            "by_source": {
                source: sum(1 for entry in self._skills.values() if entry.source == source)
                for source in ("builtin", "learned", "dynamic")
            },
            "top_used": sorted(
                [(entry.skill.name, entry.call_count) for entry in self._skills.values()],
                key=lambda item: item[1],
                reverse=True,
            )[:5],
        }

    @classmethod
    def instance(cls) -> "SkillRegistry":
        return cls()
