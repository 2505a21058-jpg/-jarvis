from __future__ import annotations

import json

from agent.intent.classifier import classify
from agent.intent.schema import IntentName
from skills.learned import extract_trigger_phrases, get_all_learned_skills, store_learned_skill


def test_extract_trigger_phrases_uses_explicit_phrases():
    phrases = extract_trigger_phrases(
        {
            "name": "open_youtube",
            "trigger_phrases": ["Open YouTube", " launch youtube "],
        }
    )

    assert phrases == ["open youtube", "launch youtube"]


def test_extract_trigger_phrases_infers_from_skill_name():
    phrases = extract_trigger_phrases({"name": "open_dev_setup"})

    assert phrases == ["open dev setup", "launch dev setup", "start dev setup", "run dev setup"]


def test_store_learned_skill_can_persist_trigger_phrases():
    records = []

    class FakeMemory:
        def store(self, record):
            records.append(record)

    store_learned_skill(
        FakeMemory(),
        name="open_dev_setup",
        description="Open the dev setup",
        steps=[{"skill_name": "open_app", "params": {"app": "chrome"}}],
        trigger_phrases=["open my dev setup"],
    )

    payload = json.loads(records[0]["content"])
    assert payload["trigger_phrases"] == ["open my dev setup"]


def test_get_all_learned_skills_returns_persisted_definitions():
    skill_def = {
        "type": "learned_skill",
        "name": "open_dev_setup",
        "description": "Open the dev setup",
        "trigger_phrases": ["open my dev setup"],
        "steps": [{"skill_name": "open_app", "params": {"app": "chrome"}}],
    }

    class FakeMemory:
        memory_path = "memory.jsonl"

        def _read_jsonl(self, path):
            assert path == self.memory_path
            return [{"type": "learned_skill", "content": json.dumps(skill_def)}]

    assert get_all_learned_skills(FakeMemory()) == [skill_def]


def test_learned_rules_classify_exact_and_prefix_without_llm(monkeypatch):
    from agent.intent import learned_rules

    learned_rules._LEARNED_RULES.clear()
    monkeypatch.setattr(
        "agent.intent.classifier.classify_with_llm",
        lambda raw: (_ for _ in ()).throw(AssertionError("LLM should not classify learned triggers")),
    )

    count = learned_rules.register_learned_skill_rules(
        {
            "name": "open_dev_setup",
            "trigger_phrases": ["open my dev setup"],
            "steps": [],
        }
    )

    exact = classify("open my dev setup")
    prefix = classify("open my dev setup and start coding")

    assert count == 1
    assert exact.name == IntentName.UNKNOWN
    assert exact.get("__learned_skill__") == "open_dev_setup"
    assert exact.classification_source == "learned_rule"
    assert prefix.get("__learned_skill__") == "open_dev_setup"
    assert prefix.classification_source == "learned_rule_prefix"


def test_load_all_learned_rules_registers_every_skill(monkeypatch):
    from agent.intent import learned_rules

    learned_rules._LEARNED_RULES.clear()
    monkeypatch.setattr(
        "skills.learned.get_all_learned_skills",
        lambda memory=None: [
            {"name": "open_dev_setup", "trigger_phrases": ["open my dev setup"], "steps": []},
            {"name": "play_focus_music", "steps": []},
        ],
    )

    count = learned_rules.load_all_learned_rules()

    assert count == 5
    assert learned_rules._LEARNED_RULES["open my dev setup"] == ("open_dev_setup", {})
    assert learned_rules._LEARNED_RULES["stream focus music"] == ("play_focus_music", {})
