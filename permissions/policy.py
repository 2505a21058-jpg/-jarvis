from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


logger = logging.getLogger("jarvis.permissions")

DEFAULT_POLICY_PATH = Path("permissions/policy.json")


@dataclass
class PolicyResult:
    allowed: bool
    reason: str = ""
    require_confirmation: bool = False


def _default_policy() -> dict:
    return {
        "version": 1,
        "mode": "allow_all",
        "rules": [],
        "require_confirmation_for": ["send_email", "compose_email", "run_code", "computer_control"],
        "restricted_params": {
            "run_code": {
                "required_params": ["task"],
                "denied_patterns": ["rm -rf", "del /f", "format ", "shutdown", "restart"],
            },
            "send_email": {
                "required_params": ["to"],
            },
            "computer_control": {
                "required_params": ["goal"],
            },
        },
    }


class PolicyEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._policy = None
        return cls._instance

    def load(self, path: str | Path = DEFAULT_POLICY_PATH) -> None:
        resolved = Path(path)
        if resolved.exists():
            try:
                with open(resolved, "r", encoding="utf-8") as f:
                    self._policy = json.load(f)
                logger.info("Loaded permission policy from %s", resolved)
                return
            except Exception as exc:
                logger.warning("Failed to load policy from %s: %s. Using defaults.", resolved, exc)
        self._policy = _default_policy()
        self._save(resolved)

    def reload(self, path: str | Path = DEFAULT_POLICY_PATH) -> None:
        self._policy = None
        self.load(path)

    def check(self, skill_name: str, params: dict | None = None, user_input: str = "") -> PolicyResult:
        policy = self._policy or _default_policy()
        mode = policy.get("mode", "allow_all")

        params = params or {}
        rules = policy.get("rules", [])

        for rule in rules:
            rule_skill = rule.get("skill", "")
            if rule_skill and rule_skill != skill_name:
                continue
            rule_pattern = rule.get("pattern", "")
            if rule_pattern and rule_pattern not in str(user_input).lower():
                continue
            if rule.get("deny", False):
                return PolicyResult(allowed=False, reason=rule.get("reason", f"Skill '{skill_name}' denied by policy"))
            if rule.get("allow", False):
                return PolicyResult(allowed=True, require_confirmation=False)
            if rule.get("confirm", False):
                return PolicyResult(allowed=True, require_confirmation=True, reason=rule.get("reason", ""))

        restricted = policy.get("restricted_params", {}).get(skill_name, {})
        denied_patterns = restricted.get("denied_patterns", [])
        input_lower = str(user_input).lower()
        for pattern in denied_patterns:
            if pattern in input_lower or any(pattern in str(v).lower() for v in params.values()):
                return PolicyResult(allowed=False, reason=f"Action contains denied pattern: '{pattern}'")
        param_values = " ".join(str(v).lower() for v in params.values())
        for pattern in denied_patterns:
            if pattern in param_values:
                return PolicyResult(allowed=False, reason=f"Parameter contains denied pattern: '{pattern}'")

        required = restricted.get("required_params", [])
        for req in required:
            if not params.get(req):
                return PolicyResult(allowed=False, reason=f"Missing required parameter: '{req}'")

        if mode == "deny_all":
            return PolicyResult(allowed=False, reason="Policy mode is deny_all")

        if mode == "confirm_all":
            return PolicyResult(allowed=True, require_confirmation=True)

        confirm_skills = policy.get("require_confirmation_for", [])
        if skill_name in confirm_skills:
            return PolicyResult(allowed=True, require_confirmation=True)

        return PolicyResult(allowed=True)

    def stats(self) -> dict:
        policy = self._policy or _default_policy()
        return {
            "mode": policy.get("mode", "allow_all"),
            "rules_count": len(policy.get("rules", [])),
            "confirm_skills": list(policy.get("require_confirmation_for", [])),
        }

    def _save(self, path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._policy, f, indent=2)
        except Exception as exc:
            logger.debug("Failed to save default policy: %s", exc)

    @classmethod
    def instance(cls) -> PolicyEngine:
        return cls()
