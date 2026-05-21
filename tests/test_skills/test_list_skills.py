from __future__ import annotations

from skills import ListSkillsSkill, SkillBase, SkillResult


def test_list_skills_returns_skills(state):
    from skills.registry import SkillRegistry
    SkillRegistry._instance = None
    registry = SkillRegistry.instance()
    registry.register_builtin(_DummySkill())
    skill = ListSkillsSkill()
    result = skill.execute({}, state)
    assert result.success
    assert "Built-in skills:" in result.output
    assert "dummy_skill" in result.output


def test_list_skills_empty_registry(state):
    from skills.registry import SkillRegistry
    SkillRegistry._instance = None
    skill = ListSkillsSkill()
    result = skill.execute({}, state)
    assert result.success
    assert "Built-in skills:" in result.output


class _DummySkill(SkillBase):
    name = "dummy_skill"
    description = "A test skill"
    version = "1.0"

    def execute(self, params, state):
        return SkillResult(success=True, output="ok")
