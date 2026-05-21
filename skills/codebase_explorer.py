"""
skills/codebase_explorer.py

Codebase Explorer skill — searches files, reads source code,
traces imports, and optionally inspects modules at runtime to
answer questions about the Jarvis codebase itself.
"""

from __future__ import annotations

import ast
import glob as glob_mod
import importlib
import inspect
import logging
import os
import re
import sys
import time
from typing import Optional

from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.codebase_explorer")

_WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_MAX_READ_CHARS = 4000
_MAX_RUNTIME_SECONDS = 5
_SAFE_MODULES_PREFIX = ("agent", "skills", "internet", "memory", "permissions", "jconfig")

_RUNTIME_BLOCKED_KEYWORDS = (
    "os.system", "os.popen", "subprocess", "shutil.rmtree",
    "Path.unlink", "Path.rmdir", "eval(", "exec(",
)


class CodebaseExplorerSkill(SkillBase):
    name = "codebase_explorer"
    description = "Explore the Jarvis codebase — search files, read source, trace imports, or inspect modules at runtime"
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        query = str(params.get("query") or params.get("task") or "").strip()
        mode = str(params.get("mode") or "read").strip().lower()
        paths_param = params.get("paths")
        filter_pattern = str(params.get("filter") or "").strip()

        if not query and not filter_pattern:
            return SkillResult(success=False, output=None, error="Please provide a query or filter pattern.", skill_name=self.name)

        try:
            if mode == "runtime":
                answer = self._explore_runtime(query, filter_pattern, paths_param)
            else:
                answer = self._explore_static(query, filter_pattern, paths_param)
            return SkillResult(success=True, output=answer, skill_name=self.name)
        except Exception as exc:
            logger.error("[CODEEXPLORER] Error: %s", exc, exc_info=True)
            return SkillResult(success=False, output=None, error=str(exc), skill_name=self.name)

    def _discover_files(self, filter_pattern: str) -> list[str]:
        if filter_pattern:
            results = glob_mod.glob(os.path.join(_WORKSPACE, "**", filter_pattern), recursive=True)
            return sorted(r for r in results if os.path.isfile(r))
        return []

    def _grep_files(self, pattern: str) -> list[tuple[str, int, str]]:
        matches: list[tuple[str, int, str]] = []
        compiled = re.compile(pattern, re.IGNORECASE)
        src_root = os.path.join(_WORKSPACE, "src") if os.path.isdir(os.path.join(_WORKSPACE, "src")) else _WORKSPACE
        for root, _dirs, files in os.walk(src_root):
            for f in files:
                if not f.endswith(".py"):
                    continue
                path = os.path.join(root, f)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if compiled.search(line):
                                rel = os.path.relpath(path, _WORKSPACE)
                                matches.append((rel, lineno, line.rstrip()))
                except Exception:
                    pass
        return matches[:30]

    def _read_files(self, paths: list[str]) -> dict[str, str]:
        contents: dict[str, str] = {}
        for p in paths:
            abspath = p if os.path.isabs(p) else os.path.join(_WORKSPACE, p)
            if not os.path.isfile(abspath):
                continue
            try:
                with open(abspath, encoding="utf-8", errors="replace") as fh:
                    text = fh.read(_MAX_READ_CHARS)
                rel = os.path.relpath(abspath, _WORKSPACE)
                contents[rel] = text
            except Exception as exc:
                logger.debug("[CODEEXPLORER] read_failed %s: %s", p, exc)
        return contents

    def _trace_imports(self, path: str, depth: int = 2) -> list[str]:
        abspath = path if os.path.isabs(path) else os.path.join(_WORKSPACE, path)
        if not os.path.isfile(abspath):
            return []
        try:
            with open(abspath, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except SyntaxError:
            return []

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(p) for p in _SAFE_MODULES_PREFIX):
                        imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(p) for p in _SAFE_MODULES_PREFIX):
                    imports.append(node.module)

        traced = list(dict.fromkeys(imports))
        if depth > 1 and traced:
            for mod in traced[:3]:
                try:
                    module = importlib.import_module(mod)
                    mod_file = getattr(module, "__file__", "")
                    if mod_file and mod_file.endswith(".py"):
                        deeper = self._trace_imports(mod_file, depth - 1)
                        traced.extend(d for d in deeper if d not in traced)
                except Exception:
                    pass
        return traced[:10]

    def _build_static_prompt(self, query: str, contents: dict[str, str], traced: list[str]) -> str:
        lines = [f"Question about the Jarvis codebase: {query}", ""]
        lines.append("Below are the relevant source files:\n")
        for relpath, text in sorted(contents.items()):
            lines.append(f"--- {relpath} ---")
            lines.append(text[:2000])
            lines.append("")
        if traced:
            lines.append("Import chain (traced): " + ", ".join(traced))
        lines.append("\nAnswer based on the source code above.")
        return "\n".join(lines)

    def _explore_static(self, query: str, filter_pattern: str, paths_param) -> str:
        discovered: list[str] = []
        if paths_param:
            if isinstance(paths_param, str):
                discovered = [p.strip() for p in paths_param.split(",") if p.strip()]
            elif isinstance(paths_param, list):
                discovered = list(paths_param)
        if filter_pattern:
            discovered.extend(self._discover_files(filter_pattern))
        if not discovered and query:
            keywords = re.sub(r"[^\w\s]", "", query).split()
            for kw in keywords[:3]:
                if len(kw) >= 3:
                    matches = self._grep_files(kw)
                    seen_paths = set(discovered)
                    for path, _lineno, _line in matches:
                        if path not in seen_paths:
                            seen_paths.add(path)
                            discovered.append(path)

        if not discovered:
            discovered = ["agent/executor.py", "agent/computer_use.py"]

        contents = self._read_files(discovered[:8])
        traced = self._trace_imports(list(contents.keys())[0]) if contents else []
        prompt = self._build_static_prompt(query, contents, traced)
        return self._call_llm(prompt)

    def _explore_runtime(self, query: str, filter_pattern: str, paths_param) -> str:
        discovered: list[str] = []
        if paths_param:
            if isinstance(paths_param, str):
                discovered = [p.strip() for p in paths_param.split(",") if p.strip()]
            elif isinstance(paths_param, list):
                discovered = list(paths_param)
        if not discovered and filter_pattern:
            discovered = self._discover_files(filter_pattern)
        if not discovered:
            discovered = ["agent/executor.py"]

        contents = self._read_files(discovered[:5])
        runtime_info: list[str] = []
        for path in list(contents.keys())[:3]:
            mod_name = path.replace(os.sep, ".").replace(".py", "")
            try:
                mod = importlib.import_module(mod_name)
                classes = inspect.getmembers(mod, inspect.isclass)
                funcs = inspect.getmembers(mod, inspect.isfunction)
                runtime_info.append(f"Module: {mod_name}")
                if classes:
                    runtime_info.append("  Classes: " + ", ".join(c[0] for c in classes[:10]))
                if funcs:
                    runtime_info.append("  Functions: " + ", ".join(f[0] for f in funcs[:10]))
            except Exception as exc:
                runtime_info.append(f"Module {mod_name}: import error {exc}")

        prompt = (
            f"Question about Jarvis codebase: {query}\n\n"
            "Source files:\n"
        )
        for relpath, text in sorted(contents.items()):
            prompt += f"\n--- {relpath} ---\n{text[:3000]}\n"
        if runtime_info:
            prompt += "\nRuntime introspection:\n" + "\n".join(runtime_info)
        prompt += "\n\nAnswer based on the source code and runtime inspection."
        return self._call_llm(prompt)

    def _call_llm(self, prompt: str) -> str:
        from models.llm import call_llm
        system = "You are a senior software engineer analyzing the Jarvis codebase. Be specific and reference actual code."
        response = call_llm(
            system=system,
            user=prompt,
            temperature=0.2,
            max_tokens=800,
            timeout=25,
        )
        return response.strip() or "I could not analyze the codebase."
