from __future__ import annotations

from skills.base import SkillBase, SkillResult


class DummySkill(SkillBase):
    name = "dummy_skill"
    description = "Test skill"

    def execute(self, params, state):
        return SkillResult(success=True, output="v1")


class DummySkillV2(SkillBase):
    name = "dummy_skill"
    description = "Test skill v2"

    def execute(self, params, state):
        return SkillResult(success=True, output="v2")


def test_register_builtin(registry):
    registry.register_builtin(DummySkill())
    entry = registry.get_entry("dummy_skill")
    assert entry.source == "builtin"
    assert entry.version == 1


def test_learned_cannot_override_builtin(registry):
    registry.register_builtin(DummySkill())
    result = registry.register_learned(DummySkillV2())
    assert result is False
    assert registry.get_entry("dummy_skill").source == "builtin"


def test_learned_overrides_learned(registry):
    registry.register_learned(DummySkill())
    registry.register_learned(DummySkillV2())
    entry = registry.get_entry("dummy_skill")
    assert entry.version == 2
    assert entry.skill.execute({}, None).output == "v2"


def test_execute_unknown(registry):
    result = registry.execute("nonexistent", {}, None)
    assert not result.success
    assert "Unknown skill" in result.error


def test_call_count(registry):
    registry.register_builtin(DummySkill())
    registry.execute("dummy_skill", {}, None)
    registry.execute("dummy_skill", {}, None)
    assert registry.get_entry("dummy_skill").call_count == 2


def test_remove_learned(registry):
    registry.register_learned(DummySkill())
    assert registry.remove("dummy_skill") is True
    assert registry.get("dummy_skill") is None


def test_remove_builtin_blocked(registry):
    registry.register_builtin(DummySkill())
    assert registry.remove("dummy_skill") is False


def test_list_skills_metadata(registry):
    registry.register_builtin(DummySkill())
    skills = registry.list_skills()
    assert skills[0]["source"] == "builtin"
    assert "version" in skills[0]
