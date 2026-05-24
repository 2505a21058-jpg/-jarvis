"""Filesystem safety helpers for local-file skills."""

from __future__ import annotations

import os
from pathlib import Path

_ALLOWED_ROOTS_ENV = "JARVIS_ALLOWED_FILE_ROOTS"
_ALLOW_ALL_ENV = "JARVIS_ALLOW_ALL_LOCAL_FILES"

_SENSITIVE_DIRS = {
    ".aws",
    ".azure",
    ".config/gcloud",
    ".gcloud",
    ".gnupg",
    ".kube",
    ".ssh",
}
_SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
    "token.json",
}
_SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx")


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _expand_path(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).resolve(strict=False)


def _split_allowed_roots(raw: str) -> list[Path]:
    roots: list[Path] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(_expand_path(part))
    return roots


def allowed_file_roots() -> list[Path]:
    """Return deployment-configured roots that local-file skills may access."""
    configured = os.getenv(_ALLOWED_ROOTS_ENV, "").strip()
    if configured:
        return _split_allowed_roots(configured)

    roots = [_expand_path(Path.cwd())]
    home = Path.home()
    for base in (home, home / "OneDrive"):
        for name in ("Desktop", "Documents", "Downloads"):
            candidate = base / name
            if candidate.exists():
                roots.append(_expand_path(candidate))

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        marker = os.path.normcase(str(root))
        if marker not in seen:
            seen.add(marker)
            deduped.append(root)
    return deduped


def allowed_search_roots() -> list[str]:
    """Return existing directories suitable for filesystem search."""
    roots = []
    for root in allowed_file_roots():
        if root.exists() and root.is_dir():
            roots.append(str(root))
    return roots


def _is_within(candidate: Path, root: Path) -> bool:
    candidate_text = os.path.normcase(str(candidate))
    root_text = os.path.normcase(str(root))
    try:
        return os.path.commonpath([candidate_text, root_text]) == root_text
    except ValueError:
        return False


def is_sensitive_path(path: str | os.PathLike[str]) -> bool:
    candidate = _expand_path(path)
    parts = [part.lower() for part in candidate.parts]
    joined = "/".join(parts)
    if any(part in _SENSITIVE_DIRS for part in parts):
        return True
    if any(marker in joined for marker in _SENSITIVE_DIRS):
        return True
    name = candidate.name.lower()
    return name in _SENSITIVE_FILENAMES or name.endswith(_SENSITIVE_SUFFIXES)


def path_policy_error(path: str | os.PathLike[str]) -> str | None:
    """Return a user-facing denial reason, or None when access is allowed."""
    if _truthy_env(_ALLOW_ALL_ENV):
        return None

    candidate = _expand_path(path)
    if is_sensitive_path(candidate):
        return (
            "Access denied: path appears to contain credentials or secrets. "
            f"Move a redacted copy under an allowed root, or set {_ALLOW_ALL_ENV}=true for a trusted local session."
        )

    roots = allowed_file_roots()
    if not roots or not any(_is_within(candidate, root) for root in roots):
        return (
            "Access denied: path is outside allowed file roots. "
            f"Set {_ALLOWED_ROOTS_ENV} to an os.pathsep-separated allowlist if this deployment needs broader access."
        )

    return None
