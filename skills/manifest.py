"""Agentskills.io-compatible skill manifest format.

Supports both SKILL.md (agentskills.io spec) and skill.toml (OpenJarvis-style) formats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


_SKILL_MD_DIVIDER_RE = re.compile(r'^---\s*$', re.MULTILINE)


@dataclass
class SkillManifestStep:
    name: str
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillManifest:
    name: str
    description: str
    version: str = "0.1.0"
    steps: list[SkillManifestStep] = field(default_factory=list)
    license: str = ""
    author: str = ""
    compatibility: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    instructions: str = ""
    source_path: str = ""

    def jarvis_name(self) -> str:
        """Convert manifest name (hyphens) to Jarvis skill name (underscores)."""
        return self.name.replace("-", "_")


def parse_skill_md(path: str | Path) -> SkillManifest:
    """Parse a SKILL.md file (agentskills.io format)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    match = list(_SKILL_MD_DIVIDER_RE.finditer(text))
    if len(match) >= 2:
        yaml_text = text[match[0].end():match[1].start()].strip()
        body = text[match[1].end():].strip()
    else:
        yaml_text = ""
        body = text.strip()

    import yaml
    data = yaml.safe_load(yaml_text) or {}

    raw_steps = data.get("steps", [])
    steps = []
    for s in raw_steps:
        if isinstance(s, str):
            steps.append(SkillManifestStep(name=s))
        elif isinstance(s, dict):
            steps.append(SkillManifestStep(
                name=s.get("name", ""),
                description=s.get("description", ""),
                params=s.get("params", {}),
            ))

    raw_tags = data.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",")]

    default_name = path.stem
    if default_name.endswith(".skill"):
        default_name = default_name[:-6]

    return SkillManifest(
        name=str(data.get("name", default_name)).lower(),
        description=str(data.get("description", "")),
        version=str(data.get("version", "0.1.0")),
        steps=steps,
        license=str(data.get("license", "")),
        author=str(data.get("author", "")),
        compatibility=str(data.get("compatibility", "")),
        tags=raw_tags,
        metadata=data.get("metadata", {}),
        allowed_tools=data.get("allowed-tools", []),
        instructions=body,
        source_path=str(path),
    )


def parse_skill_toml(path: str | Path) -> SkillManifest | None:
    """Parse a skill.toml file (OpenJarvis-style)."""
    path = Path(path)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            return None

    with open(path, "rb") as f:
        data = tomllib.load(f)

    skill = data.get("skill", data)
    raw_steps = skill.get("steps", [])
    steps = []
    for s in raw_steps:
        if isinstance(s, str):
            steps.append(SkillManifestStep(name=s))
        elif isinstance(s, dict):
            steps.append(SkillManifestStep(
                name=s.get("name", ""),
                description=s.get("description", ""),
                params=s.get("params", {}),
            ))

    meta = skill.get("metadata", {}) or {}

    return SkillManifest(
        name=str(skill.get("name", path.parent.stem)).lower(),
        description=str(skill.get("description", "")),
        version=str(skill.get("version", "0.1.0")),
        steps=steps,
        license=str(skill.get("license", "")),
        author=meta.get("author", ""),
        compatibility=str(skill.get("compatibility", "")),
        tags=skill.get("tags", []),
        metadata=meta,
        allowed_tools=skill.get("allowed-tools", []),
        instructions=data.get("instructions", ""),
        source_path=str(path),
    )


def load_manifest(path: str | Path) -> SkillManifest | None:
    """Auto-detect format and parse a skill manifest file."""
    path = Path(path)
    if not path.exists():
        return None
    name_lower = path.name.lower()
    if name_lower == "skill.md":
        return parse_skill_md(path)
    elif name_lower == "skill.toml":
        return parse_skill_toml(path)
    elif path.suffix.lower() == ".md":
        return parse_skill_md(path)
    elif path.suffix.lower() == ".toml":
        return parse_skill_toml(path)
    return None


def make_skill_md(manifest: SkillManifest) -> str:
    """Generate SKILL.md content from a manifest."""
    lines = ["---"]
    lines.append(f"name: {manifest.name}")
    lines.append(f"description: {manifest.description}")
    if manifest.version != "0.1.0":
        lines.append(f"version: {manifest.version}")
    if manifest.license:
        lines.append(f"license: {manifest.license}")
    if manifest.author:
        lines.append(f"author: {manifest.author}")
    if manifest.compatibility:
        lines.append(f"compatibility: {manifest.compatibility}")
    if manifest.tags:
        lines.append(f"tags: {manifest.tags!r}")
    if manifest.allowed_tools:
        lines.append(f"allowed-tools: {manifest.allowed_tools!r}")
    if manifest.metadata:
        lines.append("metadata:")
        for k, v in manifest.metadata.items():
            lines.append(f"  {k}: {v!r}")
    if manifest.steps:
        lines.append("steps:")
        for step in manifest.steps:
            if step.description:
                lines.append(f"  - name: {step.name}")
                lines.append(f"    description: {step.description}")
            else:
                lines.append(f"  - {step.name}")
    lines.append("---")
    if manifest.instructions:
        lines.append("")
        lines.append(manifest.instructions)
    return "\n".join(lines)


def make_skill_toml(manifest: SkillManifest) -> str:
    """Generate skill.toml content from a manifest."""
    lines = ["[skill]"]
    lines.append(f'name = "{manifest.name}"')
    lines.append(f'description = "{manifest.description}"')
    if manifest.version != "0.1.0":
        lines.append(f'version = "{manifest.version}"')
    if manifest.compatibility:
        lines.append(f'compatibility = "{manifest.compatibility}"')
    if manifest.tags:
        lines.append(f"tags = {manifest.tags!r}")
    lines.append(f"steps = {[s.name for s in manifest.steps]!r}")
    if manifest.metadata:
        lines.append("[skill.metadata]")
        for k, v in manifest.metadata.items():
            lines.append(f'{k} = {v!r}')
    return "\n".join(lines)
