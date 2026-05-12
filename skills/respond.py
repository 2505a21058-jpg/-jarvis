"""
skills/respond.py

The respond skill generates a natural language response via LLM.
Used by the planner when a step requires text output rather than a
physical action.
"""

import logging

from skills.base import SkillBase, SkillResult

logger = logging.getLogger("jarvis.skills.respond")


class RespondSkill(SkillBase):
    name = "respond"
    description = "Generates a natural language response or answer"
    timeout_seconds = 15.0

    def execute(self, params: dict, state) -> SkillResult:
        message = params.get("message", "").strip()
        query = params.get("query", params.get("content", message)).strip()

        if not query:
            return SkillResult(success=True, output="Done.", skill_name=self.name)

        try:
            from models.llm import call_llm

            response = call_llm(
                system=(
                    "You are Jarvis, a helpful AI assistant. "
                    "Answer the query clearly and concisely. "
                    "No reasoning headers. No 'Answer:' prefix. Just the response."
                ),
                user=query,
                temperature=0.7,
                max_tokens=512,
            )
            return SkillResult(success=True, output=response.strip(), skill_name=self.name)
        except Exception as exc:
            logger.error("RespondSkill LLM call failed: %s", exc)
            return SkillResult(
                success=False,
                output=None,
                error=str(exc),
                skill_name=self.name,
            )
