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


class BuiltinVersionedSkill(SkillBase):
    name = "versioned_builtin"
    description = "Versioned built-in"
    version = "2.3"

    def execute(self, params, state):
        return SkillResult(success=True, output="builtin")


def test_register_builtin(registry):
    registry.register_builtin(DummySkill())
    entry = registry.get_entry("dummy_skill")
    assert entry.source == "builtin"
    assert entry.version == "1.0"


def test_learned_cannot_override_builtin(registry):
    registry.register_builtin(DummySkill())
    result = registry.register_learned(DummySkillV2())
    assert result is False
    assert registry.get_entry("dummy_skill").source == "builtin"
    assert registry.get("dummy_skill").execute({}, None).output == "v1"
    assert registry.get_entry("learned_dummy_skill").source == "learned"
    assert registry.get_entry("learned_dummy_skill").version == "1.0"
    assert registry.get("learned_dummy_skill").execute({}, None).output == "v2"


def test_force_allows_learned_override_of_builtin(registry):
    registry.register_builtin(DummySkill())
    result = registry.register(DummySkillV2(), source="learned", force=True)
    entry = registry.get_entry("dummy_skill")

    assert result is True
    assert entry.source == "learned"
    assert entry.version == "1.1"
    assert registry.get("dummy_skill").execute({}, None).output == "v2"
    assert registry.list_skills_verbose()[0]["forced_override"] is True


def test_learned_overrides_learned(registry):
    registry.register_learned(DummySkill())
    registry.register_learned(DummySkillV2())
    entry = registry.get_entry("dummy_skill")
    assert entry.version == "1.1"
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


def test_builtin_uses_declared_semver(registry):
    registry.register_builtin(BuiltinVersionedSkill())

    entry = registry.get_entry("versioned_builtin")
    verbose = registry.list_skills_verbose()[0]

    assert entry.version == "2.3"
    assert verbose["version"] == "2.3"
    assert verbose["source"] == "builtin"


def test_list_skills_verbose_reports_conflict_metadata(registry):
    registry.register_builtin(DummySkill())
    registry.register_learned(DummySkillV2())

    skills = {skill["name"]: skill for skill in registry.list_skills_verbose()}

    assert skills["dummy_skill"]["source"] == "builtin"
    assert skills["dummy_skill"]["version"] == "1.0"
    assert skills["dummy_skill"]["conflict"] is False
    assert skills["learned_dummy_skill"]["source"] == "learned"
    assert skills["learned_dummy_skill"]["version"] == "1.0"
    assert skills["learned_dummy_skill"]["conflict"] is True
    assert skills["learned_dummy_skill"]["original_name"] == "dummy_skill"


def test_list_skills_skill_groups_builtin_and_learned(registry, monkeypatch):
    import skills

    registry.register_builtin(DummySkill())
    registry.register_learned(DummySkillV2())
    monkeypatch.setattr(skills.SkillRegistry, "instance", lambda: registry)

    result = skills.ListSkillsSkill().execute({}, None)

    assert result.success is True
    assert "Built-in skills:" in result.output
    assert "dummy_skill (v1.0)" in result.output
    assert "Learned skills:" in result.output
    assert "learned_dummy_skill (v1.0)" in result.output
    assert "conflicts with built-in" in result.output


def test_get_registry_bootstraps_and_returns_registry(monkeypatch):
    import skills

    calls = []
    monkeypatch.setattr(skills, "bootstrap_skills", lambda: calls.append("bootstrapped") or "registry")

    assert skills.get_registry() == "registry"
    assert calls == ["bootstrapped"]


def test_get_registry_repopulates_after_singleton_reset(monkeypatch):
    import skills
    from skills.registry import SkillRegistry

    monkeypatch.setattr(skills, "_BOOTSTRAPPED", True)
    SkillRegistry._instance = None

    registry = skills.get_registry()

    assert registry.get("open_app") is not None
