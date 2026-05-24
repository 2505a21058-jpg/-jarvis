"""Tests for SkillCatalog — discovery, loading, XML catalog."""
from __future__ import annotations

from pathlib import Path

from skills.catalog import AgentSkill, CatalogSkill, SkillCatalog
from skills.manifest import make_skill_md


def _write_manifest(dir: Path, name: str, steps: list[str] | None = None,
                     description: str = "test") -> Path:
    """Write a minimal .skill.md manifest into dir."""
    steps_block = ""
    if steps is not None:
        steps_block = "\n".join(f"  - {s}" for s in steps)
        steps_yaml = f"\nsteps:\n{steps_block}" if steps_block else ""
    else:
        steps_yaml = ""

    content = f"""---
name: {name}
description: {description}{steps_yaml}
---
"""
    filepath = dir / f"{name}.skill.md"
    filepath.write_text(content, encoding="utf-8")
    return filepath


def test_discover_manifests_dir(tmp_path):
    _write_manifest(tmp_path, "open-search", steps=["open", "search"])
    _write_manifest(tmp_path, "select-type", steps=["select", "type"])

    catalog = SkillCatalog(tmp_path)
    manifests = catalog.discover()

    assert len(manifests) == 2
    assert "open_search" in manifests
    assert "select_type" in manifests
    assert manifests["open_search"].description == "test"


def test_discover_catalog_subdirs(tmp_path):
    agent_dir = tmp_path / "my-researcher"
    agent_dir.mkdir()
    (agent_dir / "SKILL.md").write_text("""---
name: my-researcher
description: Researches topics
---

Use web search to find information.
""", encoding="utf-8")

    catalog = SkillCatalog(tmp_path)
    manifests = catalog.discover()

    assert len(manifests) == 1
    assert "my_researcher" in manifests
    assert manifests["my_researcher"].steps == []


def test_discover_empty_dir(tmp_path):
    catalog = SkillCatalog(tmp_path)
    manifests = catalog.discover()
    assert manifests == {}


def test_get_catalog_xml(tmp_path):
    _write_manifest(tmp_path, "open-search", steps=["open", "search"],
                    description="Opens and searches")
    _write_manifest(tmp_path, "type-only", steps=["type"],
                    description="Types text")

    catalog = SkillCatalog(tmp_path)
    catalog.discover()
    xml = catalog.get_catalog_xml()

    assert "<available_skills>" in xml
    assert "</available_skills>" in xml
    assert 'name="open-search"' in xml
    assert 'name="type-only"' in xml
    assert 'steps="open,search"' in xml
    assert 'steps="type"' in xml
    assert 'description="Opens and searches"' in xml


def test_load_skills(tmp_path):
    _write_manifest(tmp_path, "open-search", steps=["open", "search"])
    agent_md = tmp_path / "researcher.skill.md"
    agent_md.write_text("""---
name: researcher
description: Researches topics
---

Instructions here.
""", encoding="utf-8")

    catalog = SkillCatalog(tmp_path)
    catalog.discover()
    catalog.load_skills()

    assert len(catalog._skills) == 2
    assert isinstance(catalog._skills["open_search"], CatalogSkill)
    assert isinstance(catalog._skills["researcher"], AgentSkill)
    assert catalog._skills["open_search"].STEPS == ["open", "search"]
    assert catalog._skills["researcher"].STEPS == []


def test_deduplication_first_seen_wins(tmp_path):
    dir1 = tmp_path / "a"
    dir2 = tmp_path / "b"
    dir1.mkdir()
    dir2.mkdir()
    _write_manifest(dir1, "open-search", steps=["open", "search"],
                    description="first version")
    _write_manifest(dir2, "open-search", steps=["open"],
                    description="second version")

    catalog = SkillCatalog(dir1, dir2)
    manifests = catalog.discover()

    assert len(manifests) == 1
    assert len(manifests["open_search"].steps) == 2
    assert manifests["open_search"].steps[0].name == "open"
    assert manifests["open_search"].steps[1].name == "search"


def test_register_catalog_skills(tmp_path):
    from skills.base import SkillBase
    from skills.registry import SkillRegistry

    SkillRegistry._instance = None
    registry = SkillRegistry.instance()

    _write_manifest(tmp_path, "open-search", steps=["open", "search"])
    agent_md = tmp_path / "researcher.skill.md"
    agent_md.write_text("""---
name: researcher
description: Researches topics
---

Instructions here.
""", encoding="utf-8")

    catalog = SkillCatalog(tmp_path)
    count = catalog.register_catalog_skills(registry)

    assert count == 2
    assert registry.get("open_search") is not None
    assert registry.get("researcher") is not None
    assert isinstance(registry.get("open_search"), CatalogSkill)
    assert isinstance(registry.get("researcher"), AgentSkill)
