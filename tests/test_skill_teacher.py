from __future__ import annotations


def test_teach_skill_registers_learned_gate_rules(monkeypatch, memory):
    import agent.skill_teacher as skill_teacher

    skill_def = {
        "name": "open_dev_setup",
        "description": "Open the dev setup",
        "trigger_phrases": ["open my dev setup"],
        "steps": [{"skill_name": "open_app", "params": {"app": "chrome"}}],
    }
    registered = []

    class FakeRegistry:
        def register_learned(self, skill):
            return True

    monkeypatch.setattr(skill_teacher, "extract_skill_from_instruction", lambda raw: skill_def)
    monkeypatch.setattr(skill_teacher, "store_learned_skill", lambda **kwargs: None)
    monkeypatch.setattr(skill_teacher.SkillRegistry, "instance", lambda: FakeRegistry())
    monkeypatch.setattr("agent.gate_rule_generator.generate_rule_for_skill", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "agent.intent.learned_rules.register_learned_skill_rules",
        lambda new_skill_def: registered.append(new_skill_def) or 1,
    )

    response = skill_teacher.teach_skill("teach you to open my dev setup", memory)

    assert "Learned new skill: 'open_dev_setup'" in response
    assert registered == [skill_def]
