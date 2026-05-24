"""Tests for SkillManifest parsing, generation, and conversion."""

from __future__ import annotations

from pathlib import Path

from skills.catalog import AgentSkill, CatalogSkill
from skills.manifest import (
    SkillManifest,
    load_manifest,
    make_skill_md,
    parse_skill_md,
)


def test_parse_skill_md_with_steps(tmp_path):
    md = tmp_path / "open-search.skill.md"
    md.write_text("""---
name: open-search
description: Opens an app and searches
steps:
  - open
  - search
---
""", encoding="utf-8")

    manifest = parse_skill_md(md)
    assert manifest.name == "open-search"
    assert manifest.description == "Opens an app and searches"
    assert len(manifest.steps) == 2
    assert manifest.steps[0].name == "open"
    assert manifest.steps[1].name == "search"


def test_parse_skill_md_without_steps(tmp_path):
    md = tmp_path / "researcher.skill.md"
    md.write_text("""---
name: researcher
description: Researches any topic
---

Use web search and summarization to research the given topic.
""", encoding="utf-8")

    manifest = parse_skill_md(md)
    assert manifest.name == "researcher"
    assert manifest.description == "Researches any topic"
    assert manifest.steps == []
    assert "web search" in manifest.instructions


def test_parse_skill_md_tags_compatibility(tmp_path):
    md = tmp_path / "full.skill.md"
    md.write_text("""---
name: full-skill
description: A fully specified skill
version: "2.0"
tags:
  - browser
  - automation
compatibility: Requires Playwright
metadata:
  author: jarvis
  rating: "5"
allowed-tools:
  - Read
  - Bash
---
Full instructions here.
""", encoding="utf-8")

    manifest = parse_skill_md(md)
    assert manifest.version == "2.0"
    assert manifest.tags == ["browser", "automation"]
    assert manifest.compatibility == "Requires Playwright"
    assert manifest.metadata["author"] == "jarvis"
    assert manifest.allowed_tools == ["Read", "Bash"]


def test_parse_skill_md_no_frontmatter(tmp_path):
    md = tmp_path / "plain.skill.md"
    md.write_text("Just some markdown without frontmatter.\n", encoding="utf-8")

    manifest = parse_skill_md(md)
    assert manifest.name == "plain"
    assert manifest.description == ""
    assert manifest.steps == []
    assert "Just some markdown" in manifest.instructions


def test_parse_skill_toml_format(tmp_path):
    toml_file = tmp_path / "skill.toml"
    toml_file.write_text("""[skill]
name = "data-pipeline"
description = "Extract, transform, and load data"
steps = ["open", "search", "select", "type"]
version = "0.5.0"
tags = ["data", "etl"]

[skill.metadata]
author = "jarvis"
""", encoding="utf-8")

    manifest = load_manifest(toml_file)
    assert manifest is not None
    assert manifest.name == "data-pipeline"
    assert len(manifest.steps) == 4
    assert manifest.steps[0].name == "open"
    assert manifest.version == "0.5.0"
    assert manifest.tags == ["data", "etl"]


def test_jarvis_name_conversion():
    m = SkillManifest(name="open-search", description="test")
    assert m.jarvis_name() == "open_search"

    m2 = SkillManifest(name="simple", description="test")
    assert m2.jarvis_name() == "simple"


def test_manifest_to_skill_catalog():
    manifest = SkillManifest(
        name="open-search",
        description="test",
        steps=[
            type("Step", (), {"name": "open", "description": "", "params": {}})(),
        ],
    )
    skill = _convert(manifest)
    assert isinstance(skill, CatalogSkill)
    assert skill.name == "open_search"
    assert skill.STEPS == ["open"]


def test_manifest_to_skill_agent():
    manifest = SkillManifest(
        name="researcher",
        description="test",
        steps=[],
        instructions="Research the topic.",
    )
    skill = _convert(manifest)
    assert isinstance(skill, AgentSkill)
    assert skill.name == "researcher"
    assert skill.STEPS == []


def test_make_skill_md_roundtrip(tmp_path):
    original = SkillManifest(
        name="roundtrip-test",
        description="Testing roundtrip",
        version="1.0",
        steps=[
            type("Step", (), {"name": "open", "description": "", "params": {}})(),
            type("Step", (), {"name": "search", "description": "", "params": {}})(),
        ],
        tags=["test"],
        compatibility="None",
        instructions="Do the thing.",
    )

    md_content = make_skill_md(original)
    md_file = tmp_path / "roundtrip-test.skill.md"
    md_file.write_text(md_content, encoding="utf-8")

    parsed = parse_skill_md(md_file)
    assert parsed.name == original.name
    assert parsed.description == original.description
    assert len(parsed.steps) == len(original.steps)
    assert parsed.steps[0].name == original.steps[0].name
    assert parsed.steps[1].name == original.steps[1].name
    assert parsed.tags == original.tags
    assert parsed.instructions == original.instructions


def _convert(manifest):
    """Mirrors manifest_to_skill logic without importing catalog directly."""
    from skills.catalog import manifest_to_skill
    return manifest_to_skill(manifest)
