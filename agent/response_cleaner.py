"""
agent/response_cleaner.py

Strips internal reasoning artifacts from LLM responses before
they reach the user. Catches leaked prompt structure, internal
state dumps, and implementation details.
"""

from __future__ import annotations

import logging
import re


logger = logging.getLogger("jarvis.response_cleaner")

_LEAKED_REASONING_PATTERNS = [
    (r"^\s*\*?\*?Answer:\*?\*?\s*", ""),
    (r"\s*\*?\*?(?:Reasoning|Explanation|Note|Context):\*?\*?.*$", ""),
    (
        r"(?:The )?(?:active_platform|active_app|task_stack_depth|search_engine|active app|active platform|task stack depth|search engine)\s*"
        r"(?:is\s+)?['\"]?[\w\s.-]+['\"]?[,.]?\s*",
        "",
    ),
    (r"(?:The )?task stack depth of \d+ indicates[^.]+\.", ""),
    (r"(?:The )?current context (?:shows|indicates)[^.]+\.", ""),
    (r"(?:The )?active platform is[^.]+\.", ""),
    (r"App not found: \w+\.", ""),
    (r"tool (?:failure|failure message)[^.]+\.", ""),
    (r"As indicated by the tool[^.]+\.", ""),
    (r"^\s*\*?\*?(?:Explanation|Reasoning|Context|Note):\*?\*?\s*\n", ""),
]

_COMPILED_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.DOTALL), replacement)
    for pattern, replacement in _LEAKED_REASONING_PATTERNS
]

_USELESS_RESPONSE_INDICATORS = [
    "no results found",
    "app not found",
    "no active app is set",
    "active app is not set",
    "active app is not",
    "i am unable to directly access",
    "since the task stack depth",
    "the current context shows",
    "i don't have the capability to",
]

_FALLBACK_RESPONSES = {
    "app_not_found": (
        "I couldn't find that app on your system. Try specifying the full app name, "
        "or say 'open [appname].com' to open it in your browser."
    ),
    "no_active_app": "I need an active app to type into. Try opening an app first, like 'open notepad'.",
    "web_resource": "I can't directly access files or download content yet. I can open a browser for you. Just say 'go to [url]'.",
    "generic_failure": "I wasn't able to complete that. Could you rephrase or give me more detail?",
}


def clean_response(response: str, decision: dict | None = None) -> str:
    """
    Remove leaked reasoning artifacts from LLM responses.
    Returns a clean, user-facing string.
    """
    _ = decision
    if not response or not response.strip():
        return response

    original = response
    cleaned = response

    for pattern, replacement in _COMPILED_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"^\s+", "", cleaned)
    cleaned = cleaned.strip()

    if len(cleaned) < 10:
        logger.debug("Response over-cleaned (len=%s), using original", len(cleaned))
        cleaned = original.strip()

    cleaned_lower = cleaned.lower()
    if any(indicator in cleaned_lower for indicator in _USELESS_RESPONSE_INDICATORS):
        if "app not found" in cleaned_lower or "couldn't find" in cleaned_lower:
            fallback = _FALLBACK_RESPONSES["app_not_found"]
        elif "no active app" in cleaned_lower or "active app" in cleaned_lower or "typing" in cleaned_lower:
            fallback = _FALLBACK_RESPONSES["no_active_app"]
        elif "external resources" in cleaned_lower or "download" in cleaned_lower:
            fallback = _FALLBACK_RESPONSES["web_resource"]
        else:
            fallback = _FALLBACK_RESPONSES["generic_failure"]

        logger.debug("Replaced useless response with fallback: %s", fallback[:50])
        return fallback

    if cleaned != original:
        logger.debug("Response cleaned: %s -> %s chars", len(original), len(cleaned))

    return cleaned
