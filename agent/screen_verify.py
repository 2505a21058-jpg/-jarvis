"""
agent/screen_verify.py

Screenshot-based action verification.
Inspired by Open Interface (github.com/AmberSahdev/Open-Interface).

Takes a screenshot before and after an action, uses vision LLM
to determine if the action succeeded visually.

Optional — degrades gracefully if mss or llava not available.
"""

import logging
import time
import base64
from typing import Optional

from config import OLLAMA_GENERATE_URL, SCREENSHOT_MAX_WIDTH, VISION_MODEL, VISION_REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger("jarvis.screen_verify")

_VISION_MODEL = VISION_MODEL
_VERIFY_URL = OLLAMA_GENERATE_URL


def _take_screenshot() -> Optional[str]:
    """Take screenshot and return as base64 PNG. Returns None on failure."""
    try:
        import mss
        from PIL import Image
        import io

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # Resize to reduce tokens
            # Screenshot width is configurable so vision latency can be tuned per machine.
            max_width = SCREENSHOT_MAX_WIDTH
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG", optimize=True)
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Screenshot failed: {e}")
        return None


def _ask_vision_model(screenshot_b64: str, question: str) -> Optional[str]:
    """Ask vision LLM about a screenshot."""
    try:
        import requests
        response = requests.post(
            _VERIFY_URL,
            json={
                "model": _VISION_MODEL,
                "prompt": question,
                "images": [screenshot_b64],
                "stream": False
            },
            timeout=VISION_REQUEST_TIMEOUT_SECONDS
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        return None
    except Exception as e:
        logger.debug(f"Vision model call failed: {e}")
        return None


def verify_action_with_screenshot(
    action_description: str,
    expected_outcome: str,
    wait_seconds: float = 3.0
) -> tuple[bool, str]:
    """
    Take screenshot after action and verify it looks correct.
    
    action_description: what was just done (e.g. "opened notepad")
    expected_outcome: what should be visible (e.g. "notepad window")
    wait_seconds: how long to wait before screenshot
    
    Returns (verified, explanation).
    Falls back to True if vision model unavailable.
    """
    time.sleep(wait_seconds)
    screenshot = _take_screenshot()

    if not screenshot:
        logger.debug("Screen verify: mss unavailable, skipping visual check")
        return True, "Visual verification unavailable (mss not installed)"

    question = (
        f"I just {action_description}. "
        f"Is there evidence of '{expected_outcome}' visible on screen? "
        f"Answer only 'yes' or 'no' followed by a brief reason."
    )

    answer = _ask_vision_model(screenshot, question)
    if not answer:
        logger.debug("Screen verify: vision model unavailable, skipping")
        return True, "Visual verification unavailable (vision model not responding)"

    answer_lower = answer.lower()
    verified = answer_lower.startswith("yes")

    logger.info(f"Screen verify for '{action_description}': {answer[:100]}")
    return verified, answer


def get_screen_context() -> Optional[str]:
    """
    Get a description of what's currently on screen.
    """
    screenshot = _take_screenshot()
    if not screenshot:
        return None

    answer = _ask_vision_model(
        screenshot,
        "Describe what is currently visible on this computer screen in 1-2 sentences. Focus on the active window and any important content."
    )
    return answer
