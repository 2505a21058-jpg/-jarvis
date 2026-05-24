from __future__ import annotations

from pathlib import Path


def test_ci_runs_dependency_audit_tools():
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pip check" in workflow
    assert "pip-audit" in workflow
