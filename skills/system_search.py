"""
skills/system_search.py

Searches the local file system for files and folders.
Works on Windows, macOS, and Linux.
No external dependencies.

Params:
  query: str - file or folder name to search for
  search_type: "file" | "folder" | "any" (default: "any")
  start_path: str - where to start searching (default: user home)
  max_results: int - maximum results to return (default: 10)
"""

from __future__ import annotations

import logging
import os

from skills.base import SkillBase, SkillResult
from skills.filesystem_safety import allowed_search_roots, path_policy_error


logger = logging.getLogger("jarvis.skills.system_search")

_SKIP_DIRS = {
    "windows",
    "system32",
    "syswow64",
    "program files",
    "programdata",
    "$recycle.bin",
    "appdata\\local\\temp",
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
}

def _should_skip(path: str) -> bool:
    path_lower = path.lower()
    return any(skip in path_lower for skip in _SKIP_DIRS)


def _search_filesystem(
    query: str,
    search_type: str = "any",
    start_paths: list | None = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Walk the filesystem and find matching files/folders.
    Returns list of {name, path, type, size_mb} dicts.
    """
    query_lower = query.lower().strip()
    results = []

    explicit_start_paths = start_paths is not None
    if not start_paths:
        start_paths = allowed_search_roots()

    seen_paths = set()

    for start_path in start_paths:
        if path_policy_error(start_path):
            continue
        if not os.path.exists(start_path):
            continue
        try:
            for root, dirs, files in os.walk(start_path, topdown=True):
                if explicit_start_paths:
                    dirs[:] = [
                        dirname for dirname in dirs
                        if dirname.lower() not in _SKIP_DIRS
                    ]
                else:
                    dirs[:] = [
                        dirname for dirname in dirs
                        if not _should_skip(os.path.join(root, dirname))
                    ]

                if len(results) >= max_results:
                    return results

                if search_type in ("folder", "any"):
                    for dirname in dirs:
                        if query_lower in dirname.lower():
                            full_path = os.path.join(root, dirname)
                            if full_path not in seen_paths:
                                seen_paths.add(full_path)
                                results.append(
                                    {
                                        "name": dirname,
                                        "path": full_path,
                                        "type": "folder",
                                        "size_mb": None,
                                    }
                                )
                                if len(results) >= max_results:
                                    return results

                if search_type in ("file", "any"):
                    for filename in files:
                        if query_lower in filename.lower():
                            full_path = os.path.join(root, filename)
                            if full_path not in seen_paths:
                                seen_paths.add(full_path)
                                try:
                                    size_mb = round(os.path.getsize(full_path) / (1024 * 1024), 2)
                                except OSError:
                                    size_mb = None
                                results.append(
                                    {
                                        "name": filename,
                                        "path": full_path,
                                        "type": "file",
                                        "size_mb": size_mb,
                                    }
                                )
                                if len(results) >= max_results:
                                    return results
        except PermissionError:
            continue
        except Exception as exc:
            logger.debug("Search error in %s: %s", start_path, exc)
            continue

    return results


class SystemSearchSkill(SkillBase):
    name = "system_search"
    description = "Searches your computer for files and folders by name"
    timeout_seconds = 20.0

    def execute(self, params: dict, state) -> SkillResult:
        _ = state
        query = str(params.get("query", "")).strip()
        search_type = str(params.get("search_type", "any")).lower()
        start_path = str(params.get("start_path", "")).strip()
        max_results = int(params.get("max_results", 10))

        if not query:
            return SkillResult(
                success=False,
                output=None,
                error="No search query provided. Say 'find folder Spider Man' or 'search for notes.txt'",
            )

        if search_type not in {"file", "folder", "any"}:
            search_type = "any"

        if start_path:
            denial = path_policy_error(start_path)
            if denial:
                return SkillResult(success=False, output=None, error=denial)
            start_paths = [os.path.abspath(start_path)]
        else:
            start_paths = allowed_search_roots()
            if not start_paths:
                return SkillResult(
                    success=False,
                    output=None,
                    error="No allowed search roots are configured or available",
                )
        logger.info("Searching for '%s' (type=%s)", query, search_type)

        try:
            results = _search_filesystem(
                query=query,
                search_type=search_type,
                start_paths=start_paths,
                max_results=max_results,
            )
        except Exception as exc:
            logger.error("System search failed: %s", exc)
            return SkillResult(success=False, output=None, error=f"Search failed: {exc}")

        if not results:
            label = search_type if search_type != "any" else "files or folders"
            return SkillResult(
                success=True,
                output=f"No {label} named '{query}' found on this computer.",
            )

        lines = [f"Found {len(results)} result(s) for '{query}':"]
        for result in results:
            size_info = f" ({result['size_mb']} MB)" if result["size_mb"] is not None else ""
            lines.append(f"  [{result['type'].upper()}] {result['name']}{size_info}")
            lines.append(f"    -> {result['path']}")

        return SkillResult(success=True, output="\n".join(lines))
