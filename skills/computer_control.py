"""Permissioned computer-control skill built on the catalog ReAct runner."""

from __future__ import annotations

from skills.catalog import AgentSkill
from skills.manifest import SkillManifest


_COMPUTER_CONTROL_INSTRUCTIONS = """
You control the desktop through the available tools only.

Use small, reversible steps: open applications or sites, search, select visible
targets, type requested text, press shortcuts, scroll, wait, and close windows
when asked. Prefer deterministic tools over broad code execution.

Stop before irreversible or high-risk actions such as purchases, payments,
bookings, submissions, deletes, transfers, account changes, or sending messages
unless the user has explicitly approved that exact action in the current task.

If the screen state is unclear, explain what you need instead of guessing.
"""


class ComputerControlSkill(AgentSkill):
    name = "computer_control"
    description = "Plans and executes general app, browser, and desktop automation with safe tool use"
    timeout_seconds = 60.0

    def __init__(self):
        super().__init__(
            SkillManifest(
                name="computer-control",
                description=self.description,
                instructions=_COMPUTER_CONTROL_INSTRUCTIONS.strip(),
                tags=["automation", "desktop", "browser"],
            )
        )
        self.name = "computer_control"
        self.timeout_seconds = 60.0

    def execute(self, params: dict, state):
        goal = str(params.get("goal") or params.get("task") or params.get("query") or "").strip()
        if not goal:
            from skills.base import SkillResult

            return SkillResult(success=False, output="", error="No computer-control task provided")
        return super().execute({**params, "query": goal}, state)
