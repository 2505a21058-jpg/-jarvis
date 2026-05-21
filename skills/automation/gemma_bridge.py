"""
skills/automation/gemma_bridge.py

Bridge between Gemma model output and skill execution.
Gemma generates action descriptions -> bridge maps to skill calls.

Used when Gemma is the assigned model for an automation intent
but a skill needs structured params (not just free text).
"""

import logging

from models.gemma import call_gemma_json

logger = logging.getLogger("jarvis.gemma_bridge")

_ACTION_SYSTEM = """
You are a computer automation planner.
Given a user request, output a JSON action plan.

Format:
{
  "steps": [
    {"skill": "open_app", "params": {"app": "chrome"}},
    {"skill": "browse", "params": {"url": "https://youtube.com"}}
  ]
}

Available skills: open_app, browse, type_text, click_element,
search_web, run_code, find_file, reminder.

Rules:
- Use only listed skills
- params must match expected skill params exactly
- Keep steps minimal - only what is needed
"""


def plan_automation(user_input: str) -> list[dict]:
    """
    Use Gemma to generate an automation plan for a user request.
    Returns list of step dicts: [{"skill": ..., "params": {...}}, ...]
    """
    try:
        result = call_gemma_json(
            prompt=f"User wants to: {user_input}",
            system=_ACTION_SYSTEM,
            max_tokens=512,
        )
        steps = result.get("steps", [])
        if not isinstance(steps, list):
            logger.warning("[GEMMA BRIDGE] Invalid steps payload for: %s", user_input[:60])
            return []
        logger.info("[GEMMA BRIDGE] Generated %s steps for: %s", len(steps), user_input[:60])
        return [step for step in steps if isinstance(step, dict)]
    except Exception as e:
        logger.error("[GEMMA BRIDGE] Planning failed: %s", e)
        return []


def verify_browser_action(
    action: str,
    target: str = "",
    url: str = "",
    page_text: str = "",
    screenshot_path: str = "",
) -> bool:
    """
    Ask Gemma to verify that a browser action appears complete.
    This keeps model access centralized through models/gemma.py.
    """
    try:
        result = call_gemma_json(
            prompt=(
                f"Action: {action}\n"
                f"Target: {target}\n"
                f"Current URL: {url}\n"
                f"Screenshot path: {screenshot_path}\n"
                f"Visible page text:\n{page_text[:3000]}\n\n"
                "Did the browser action succeed?"
            ),
            system=(
                "You verify browser automation results for Jarvis. "
                "Return ONLY JSON with keys: "
                '{"success": true_or_false, "reason": "short explanation"}.'
            ),
            retries=1,
        )
        success = bool(result.get("success", False))
        logger.info("[GEMMA BRIDGE] Browser verify %s target=%s success=%s", action, target, success)
        return success
    except Exception as exc:
        logger.warning("[GEMMA BRIDGE] Browser verification failed: %s", exc)
        return False
