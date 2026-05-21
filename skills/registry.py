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
_BUILTIN_SKILL_NAMES: set[str] = set()


class SkillEntry:
    def __init__(self, skill: SkillBase, source: str = "builtin", version: str = "1.0"):
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
            cls._instance._skill_meta: dict[str, dict] = {}
            cls._instance._builtin_skills: set[str] = set()
            cls._instance._learned_skills: set[str] = set()
            _BUILTIN_SKILL_NAMES.clear()
        return cls._instance

    def _skill_name(self, skill: SkillBase) -> str:
        name = getattr(skill, "name", "") or skill.__class__.__name__.lower()
        name = str(name).strip()
        if not name:
            raise ValueError(f"Skill {type(skill).__name__} has no name set")
        return name

    def _store_entry(self, name: str, skill: SkillBase, meta: dict) -> None:
        existing = self._skills.get(name)
        entry = SkillEntry(
            skill,
            source=str(meta.get("source", "unknown")),
            version=str(meta.get("version", "1.0")),
        )
        if existing is not None:
            entry.call_count = existing.call_count
            entry.error_count = existing.error_count
        self._skills[name] = entry
        self._skill_meta[name] = dict(meta)

    def register(self, skill: SkillBase, source: str = "builtin", force: bool = False) -> bool:
        """
        Register a skill.
        source: "builtin" | "learned"
        force: if True, allows learned skill to override built-in (requires explicit intent)
        Returns True if registered, False if rejected due to conflict.
        """
        name = self._skill_name(skill)

        if source == "builtin":
            version = str(getattr(skill, "version", "1.0") or "1.0")
            self._store_entry(
                name,
                skill,
                {
                    "source": "builtin",
                    "version": version,
                    "conflict": False,
                },
            )
            self._builtin_skills.add(name)
            self._learned_skills.discard(name)
            _BUILTIN_SKILL_NAMES.add(name)
            logger.info("[REGISTRY] Registered built-in skill: %s v%s", name, version)
            return True

        if source != "learned":
            logger.warning("[REGISTRY] Unknown skill source '%s' for skill '%s'", source, name)

        if name in _BUILTIN_SKILL_NAMES and not force:
            learned_name = f"learned_{name}"
            version = self._next_version(learned_name)
            logger.warning(
                "[REGISTRY] Learned skill '%s' conflicts with a built-in skill. "
                "Built-in retained. Use force=True to override.",
                name,
            )
            self._store_entry(
                learned_name,
                skill,
                {
                    "source": "learned",
                    "version": version,
                    "original_name": name,
                    "conflict": True,
                },
            )
            self._learned_skills.add(learned_name)
            return False

        version = self._next_version(name)
        forced_override = force and name in _BUILTIN_SKILL_NAMES
        self._store_entry(
            name,
            skill,
            {
                "source": "learned",
                "version": version,
                "conflict": False,
                "forced_override": forced_override,
            },
        )
        self._learned_skills.add(name)
        if forced_override:
            self._builtin_skills.discard(name)
        logger.info("[REGISTRY] Registered learned skill: %s v%s", name, version)
        return True

    def register_builtin(self, skill: SkillBase) -> bool:
        """Convenience method for built-in skill registration."""
        return self.register(skill, source="builtin")

    def register_learned(self, skill: SkillBase, force: bool = False) -> bool:
        """Convenience method for learned skill registration (can override other learned)."""
        return self.register(skill, source="learned", force=force)

    def _next_version(self, name: str) -> str:
        """Increment minor version for existing skill, start at 1.0 for new."""
        existing = self._skill_meta.get(name, {}).get("version", "")
        if not existing:
            return "1.0"
        try:
            major, minor = str(existing).split(".", 1)
            return f"{major}.{int(minor) + 1}"
        except Exception:
            return "1.0"

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
        verbose = self.list_skills_verbose()
        return [
            {
                **skill,
                "call_count": self._skills[skill["name"]].call_count,
                "error_count": self._skills[skill["name"]].error_count,
            }
            for skill in verbose
        ]

    def list_skills_verbose(self) -> list[dict]:
        """Return skill list with version and source metadata."""
        result = []
        for name, entry in self._skills.items():
            meta = self._skill_meta.get(name, {})
            result.append(
                {
                    "name": name,
                    "source": meta.get("source", "unknown"),
                    "version": meta.get("version", "1.0"),
                    "conflict": meta.get("conflict", False),
                    "description": getattr(entry.skill, "description", ""),
                    "original_name": meta.get("original_name"),
                    "forced_override": meta.get("forced_override", False),
                }
            )
        return sorted(result, key=lambda x: (x["source"], x["name"]))

    def remove(self, name: str, allow_builtin: bool = False) -> bool:
        """Remove a skill by name. Built-ins require explicit allow_builtin=True."""
        entry = self._skills.get(name)
        if not entry:
            return False
        if entry.source == "builtin" and not allow_builtin:
            logger.warning("Refused to remove built-in skill: '%s'", name)
            return False
        del self._skills[name]
        self._skill_meta.pop(name, None)
        self._learned_skills.discard(name)
        if allow_builtin:
            self._builtin_skills.discard(name)
            _BUILTIN_SKILL_NAMES.discard(name)
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
