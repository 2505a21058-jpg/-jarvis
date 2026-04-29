"""
agent/fast_decide.py

Tier 2 routing: lightweight LLM-based intent classification.
Uses a stripped-down prompt designed to complete in <500ms on local LLMs.
Only escalates to full decide() if intent is genuinely ambiguous.
"""

from __future__ import annotations

import json
import logging

from agent.complexity_scorer import should_use_fast_decide
from models.llm import call_llm_cached


logger = logging.getLogger("jarvis.fast_decide")


FAST_DECIDE_SYSTEM = """\
Classify the user message and respond if it's conversational.

Output ONLY JSON - one of these two formats:

If conversational (chat, question, opinion):
{"type":"chat","response":"<your response here>"}

If action needed (open app, browse, search, type, system task):
{"type":"action","action_name":"<skill>","params":{}}

Valid action skill names: open_app, browse, type_text, search, system_command, list_skills

No explanation. No markdown. JSON only.\
"""


def fast_decide(user_input: str) -> dict | None:
    """
    Attempt Tier 2 classification.
    Returns a decision dict on success, or None to escalate to Tier 3.
    Input is kept under 100 chars for speed - truncate if needed.
    """
    truncated_input = user_input[:120] if len(user_input) > 120 else user_input

    try:
        raw = call_llm_cached(
            "fast_decide",
            FAST_DECIDE_SYSTEM,
            truncated_input,
            temperature=0.0,
            max_tokens=120,
        )
    except Exception as exc:
        logger.warning("fast_decide LLM call failed: %s", exc)
        return None

    try:
        raw_clean = str(raw or "").strip()
        if raw_clean.startswith("```"):
            raw_clean = raw_clean.split("```")[-2] if "```" in raw_clean else raw_clean
        data = json.loads(raw_clean)
    except json.JSONDecodeError:
        logger.debug("fast_decide non-JSON response, escalating. Raw: %s", str(raw or "")[:80])
        return None

    intent_type = data.get("type")

    if intent_type == "chat":
        response_text = str(data.get("response", "")).strip()
        if not response_text:
            return None
        return {
            "type": "fast_chat",
            "name": "respond",
            "confidence": 0.9,
            "reason": "Tier 2 chat classification",
            "requires_plan": False,
            "parameters": {},
            "direct_response": response_text,
        }

    if intent_type == "action":
        action_name = str(data.get("action_name", "")).strip()
        if not action_name:
            return None
        return {
            "type": "skill",
            "name": action_name,
            "confidence": 0.85,
            "reason": "Tier 2 action classification",
            "requires_plan": False,
            "parameters": data.get("params", {}),
        }

    return None
