"""Skill catalog — discovers and loads skills from agentskills.io manifests."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from skills.base import SkillBase, SkillResult
from skills.manifest import (
    SkillManifest,
    load_manifest,
)
from skills.step_runner import StepRunnerSkill

logger = logging.getLogger("jarvis.skills.catalog")

_MANIFEST_DIR = Path(__file__).parent / "manifests"
_CATALOG_DIR = Path(__file__).parent / "catalog"


# ---------------------------------------------------------------------------
# Tool definitions for the AgentSkill ReAct loop (OpenAI function-calling
# schema, supported natively by Ollama).
# ---------------------------------------------------------------------------
_TOOL_DEFS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "open",
            "description": "Open an app or website in the browser. Use for URLs or app names (youtube, gmail, etc.)",
            "parameters": {
                "type": "object",
                "properties": {"app": {"type": "string", "description": "URL or app name to open"}},
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search for content on a website",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "app": {"type": "string", "description": "Optional — search within this app/domain"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select",
            "description": "Click or select a target element on the page",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string", "description": "Element description to click"}},
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Type text into a focused input element",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "Text to type"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "play",
            "description": "Play media or the first search result",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Optional search query for the media"},
                    "app": {"type": "string", "description": "Optional app to search in"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the page up or down",
            "parameters": {
                "type": "object",
                "properties": {"direction": {"type": "string", "enum": ["up", "down"], "description": "Scroll direction"}},
                "required": ["direction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shortcut",
            "description": "Execute a keyboard shortcut",
            "parameters": {
                "type": "object",
                "properties": {"keys": {"type": "string", "description": "Keyboard shortcut, e.g. ctrl+s"}},
                "required": ["keys"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for a duration in seconds",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "integer", "description": "Number of seconds to wait"}},
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close",
            "description": "Close the active browser window or tab",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information and return text results. Use for general knowledge questions.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "Execute a short Python snippet and return the output. Use for calculations, data processing, etc.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Python code to execute"}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to the file"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_llm",
            "description": "Ask another LLM call for additional reasoning. Use when you need to analyze, summarize, or generate text.",
            "parameters": {
                "type": "object",
                "properties": {"prompt": {"type": "string", "description": "The prompt for the LLM"}},
                "required": ["prompt"],
            },
        },
    },
]

_MAX_REACT_TURNS = 10


def _execution_result_to_text(result: Any) -> str:
    if getattr(result, "success", False):
        return str(getattr(result, "output", "") or "")
    metadata = getattr(result, "metadata", {}) or {}
    return json.dumps(
        {
            "success": False,
            "skill": getattr(result, "skill_name", ""),
            "error": str(getattr(result, "error", "") or "Tool execution failed"),
            "requires_confirmation": bool(metadata.get("requires_confirmation", False)),
        }
    )


class CatalogSkill(StepRunnerSkill):
    """A step-runner skill created from a skill manifest."""

    def __init__(self, manifest: SkillManifest):
        self._manifest = manifest
        self.name = manifest.jarvis_name()
        self.description = manifest.description
        self.STEPS = [s.name for s in manifest.steps]
        self.compatibility = manifest.compatibility
        self.manifest_path = manifest.source_path

    def get_manifest(self) -> SkillManifest:
        return self._manifest


class AgentSkill(StepRunnerSkill):
    """An agent-driven skill from a manifest (no predefined steps).

    Uses a ReAct loop with native Ollama tool calling to dynamically plan
    and execute actions based on manifest instructions and the user's request.
    """

    def __init__(self, manifest: SkillManifest):
        self._manifest = manifest
        self.name = manifest.jarvis_name()
        self.description = manifest.description
        self.compatibility = manifest.compatibility
        self.manifest_path = manifest.source_path
        self.STEPS = []
        self.timeout_seconds = 60.0
        self.max_turns = _MAX_REACT_TURNS

    def get_manifest(self) -> SkillManifest:
        return self._manifest

    def execute(self, params: dict, state: Any) -> SkillResult:
        instructions = self._manifest.instructions
        if not instructions:
            return SkillResult(
                success=False,
                output="",
                error=f"No instructions in manifest for '{self.name}'",
            )

        user_query = params.get("query", params.get("text", ""))
        if not user_query:
            user_query = self.description

        system = (
            f"You are executing a skill named '{self.name}'.\n\n"
            f"Instructions:\n{instructions}\n\n"
            "Use the available tools to accomplish the task. "
            "Think step by step. When you have enough information, "
            "provide a final answer as a text response."
        )

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": str(user_query)},
        ]

        from models.llm import call_llm_tools

        try:
            for turn in range(self.max_turns):
                response = call_llm_tools(
                    messages=messages,
                    tools=_TOOL_DEFS,
                    temperature=0.1,
                    max_tokens=4096,
                )

                content = response.get("content")
                tool_calls = response.get("tool_calls")

                # If the model produced text content alongside tool calls, we
                # still process the calls.  A pure-text response means done.
                if content and not tool_calls:
                    return SkillResult(success=True, output=content)

                if tool_calls:
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        raw_args = fn.get("arguments", "")
                        if isinstance(raw_args, str):
                            try:
                                args = json.loads(raw_args)
                            except json.JSONDecodeError:
                                args = {}
                        else:
                            args = raw_args or {}

                        result_text = self._execute_tool(name, args, state)
                        messages.append({
                            "role": "tool",
                            "content": str(result_text),
                            "name": name,
                        })
                else:
                    error = response.get("error") or "LLM returned empty response"
                    return SkillResult(
                        success=False,
                        output="",
                        error=error,
                    )

            return SkillResult(
                success=False,
                output="",
                error=f"Agent exceeded max turns ({self.max_turns})",
            )
        finally:
            self._cleanup_browser()

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------
    def _execute_tool(self, name: str, args: dict, state: Any = None) -> str:
        """Execute a tool by name and return its result as a string."""
        # STEP_FUNCS — browser automation
        from skills.app_helpers import STEP_FUNCS

        step_fn = STEP_FUNCS.get(name)
        if step_fn is not None:
            success = step_fn(args, self)
            return json.dumps({"success": success})

        # web_search
        if name == "web_search":
            try:
                from internet.search import search as web_search_fn
                results = web_search_fn(args.get("query", ""))
                return "\n".join(
                    f"{r.position+1}. {r.title}: {r.snippet}"
                    for r in results
                )
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        # run_code
        if name == "run_code":
            from agent.executor import get_executor

            result = get_executor().execute("run_code", {"code": args.get("code", "")}, state)
            return _execution_result_to_text(result)

        # read_file
        if name == "read_file":
            from agent.executor import get_executor

            result = get_executor().execute("read_report", {"path": args.get("path", "")}, state)
            return _execution_result_to_text(result)

        # ask_llm
        if name == "ask_llm":
            prompt = args.get("prompt", "")
            try:
                from models.llm import call_llm
                result = call_llm(
                    system="You are a helpful assistant.",
                    user=str(prompt),
                    temperature=0.3,
                    max_tokens=1024,
                )
                return str(result)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return json.dumps({"error": f"Unknown tool: {name}"})


def manifest_to_skill(manifest: SkillManifest) -> SkillBase:
    """Convert a manifest into a Jarvis SkillBase."""
    if manifest.steps:
        return CatalogSkill(manifest)
    return AgentSkill(manifest)


class SkillCatalog:
    """Discovers and loads skills from manifest directories."""

    def __init__(self, *search_paths: str | Path):
        self._search_paths = [Path(p) for p in search_paths] if search_paths else []
        self._manifests: dict[str, SkillManifest] = {}
        self._skills: dict[str, SkillBase] = {}

    @classmethod
    def with_default_paths(cls) -> SkillCatalog:
        """Create a catalog using the default manifest and catalog directories."""
        return cls(_MANIFEST_DIR, _CATALOG_DIR)

    def discover(self) -> dict[str, SkillManifest]:
        """Walk all search paths and discover manifests."""
        self._manifests = {}

        for base in self._search_paths:
            search_path: Path = Path(base)
            if not search_path.exists():
                continue

            # Flat: *.skill.md, *.md, *.toml files directly in directory
            for pattern in ("*.skill.md", "*.md", "*.toml"):
                for f in sorted(search_path.glob(pattern)):
                    m = load_manifest(f)
                    if m:
                        key = m.jarvis_name()
                        if key not in self._manifests:
                            self._manifests[key] = m

            # Subdirectory: <name>/SKILL.md or <name>/skill.toml
            for child in sorted(search_path.iterdir()):
                if not child.is_dir():
                    continue
                for manifest_name in ("SKILL.md", "skill.toml"):
                    mf = child / manifest_name
                    if mf.exists():
                        m = load_manifest(mf)
                        if m:
                            key = m.jarvis_name()
                            if key not in self._manifests:
                                self._manifests[key] = m
                        break

            # Subdirectory: <name>/<name>.skill.md
            for child in sorted(search_path.iterdir()):
                if not child.is_dir():
                    continue
                mf = child / f"{child.name}.skill.md"
                if mf.exists():
                    m = load_manifest(mf)
                    if m:
                        key = m.jarvis_name()
                        if key not in self._manifests:
                            self._manifests[key] = m

        return dict(self._manifests)

    def load_skills(self) -> dict[str, SkillBase]:
        """Convert all discovered manifests into Jarvis skills."""
        self._skills = {}
        for key, manifest in self._manifests.items():
            try:
                self._skills[key] = manifest_to_skill(manifest)
            except Exception as exc:
                logger.warning("Failed to convert manifest '%s': %s", key, exc)
        return dict(self._skills)

    def get_manifest(self, name: str) -> Optional[SkillManifest]:
        return self._manifests.get(name)

    def get_skill(self, name: str) -> Optional[SkillBase]:
        return self._skills.get(name)

    def get_catalog_xml(self) -> str:
        """Generate agentskills.io-style catalog XML for system prompts."""
        parts = ["<available_skills>"]
        for name in sorted(self._manifests):
            m = self._manifests[name]
            attrs = f'name="{m.name}" description="{m.description}"'
            if m.steps:
                steps_str = ",".join(s.name for s in m.steps)
                attrs += f' steps="{steps_str}"'
            if m.tags:
                attrs += f' tags="{" ".join(m.tags)}"'
            if m.compatibility:
                attrs += f' compatibility="{m.compatibility}"'
            parts.append(f"  <skill {attrs}/>")
        parts.append("</available_skills>")
        return "\n".join(parts)

    def list_catalog(self) -> list[dict]:
        result = []
        for name in sorted(self._manifests):
            m = self._manifests[name]
            result.append({
                "name": m.name,
                "jarvis_name": m.jarvis_name(),
                "description": m.description,
                "steps": [s.name for s in m.steps],
                "tags": m.tags,
                "compatibility": m.compatibility,
                "version": m.version,
                "source_path": m.source_path,
                "loaded": name in self._skills,
            })
        return result

    def register_catalog_skills(self, registry) -> int:
        """Register all catalog skills into a SkillRegistry. Returns count."""
        self.discover()
        self.load_skills()
        count = 0
        for key, skill in self._skills.items():
            try:
                registry.register_builtin(skill)
                count += 1
            except Exception as exc:
                logger.warning("Failed to register catalog skill '%s': %s", key, exc)
        logger.info("Registered %d skills from catalog", count)
        return count


def _init_default_catalog(registry) -> SkillCatalog:
    """Initialize the default catalog and wire it into the registry."""
    catalog = SkillCatalog.with_default_paths()
    catalog.discover()
    catalog.load_skills()
    registry.catalog = catalog

    for key, skill in catalog._skills.items():
        if isinstance(skill, AgentSkill) and not registry.get(key):
            try:
                registry.register_builtin(skill)
                logger.info("Registered agent skill from catalog: %s", key)
            except Exception as exc:
                logger.warning("Failed to register agent skill '%s': %s", key, exc)

    return catalog
