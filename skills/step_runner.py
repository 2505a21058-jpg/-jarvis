"""
skills/step_runner.py

Base class for template step-runner skills.
Each template defines a STEPS list and runs them sequentially
using a single shared Playwright page (CDP → existing Chrome first).
"""

from __future__ import annotations

import time

from skills.app_helpers import STEP_FUNCS
from skills.base import SkillBase, SkillResult


class StepRunnerSkill(SkillBase):
    STEPS: list[str] = []
    timeout_seconds = 30.0

    def execute(self, params: dict, state) -> SkillResult:
        try:
            for step_name in self.STEPS:
                fn = STEP_FUNCS.get(step_name)
                if fn is None:
                    return SkillResult(success=False, output=f"Unknown step: {step_name}", error=f"Unknown step: {step_name}")
                if not fn(params, self):
                    return SkillResult(success=False, output=f"Step '{step_name}' failed", error=f"Step '{step_name}' failed")
                time.sleep(0.3)
            return SkillResult(success=True, output="Done")
        finally:
            self._cleanup_browser()

    def _cleanup_browser(self):
        if hasattr(self, '_browser') and self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if hasattr(self, '_playwright') and self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
