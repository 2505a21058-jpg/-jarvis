"""
agent/screenshot_agent/_verifier.py

Verifies whether an action succeeded by comparing screenshots
before/after and optionally asking a vision model.

Uses pixel-diff as a fast heuristic, vision model description as
a more accurate check, and falls back to trusting the executor result.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from agent.screenshot_agent._perception import _take_screenshot, _ask_vision

logger = logging.getLogger("jarvis.screenshot_agent.verifier")

_PIXEL_DIFF_THRESHOLD = 0.02
_VERIFY_WAIT_SECONDS = 1.0


def _pixel_diff(before_b64: str, after_b64: str) -> float:
    """Compute fraction of pixels that changed. Returns 0.0 if unavailable."""
    if not before_b64 or not after_b64:
        return 0.0
    try:
        import base64
        import io
        from PIL import Image
        import numpy as np

        before = Image.open(io.BytesIO(base64.b64decode(before_b64))).convert("L")
        after = Image.open(io.BytesIO(base64.b64decode(after_b64))).convert("L")

        if before.size != after.size:
            after = after.resize(before.size, Image.LANCZOS)

        arr_before = np.array(before, dtype=np.int16)
        arr_after = np.array(after, dtype=np.int16)
        diff = np.abs(arr_before.astype(np.int16) - arr_after.astype(np.int16))
        changed = np.sum(diff > 30)
        total = diff.size
        return changed / total if total > 0 else 0.0
    except Exception as exc:
        logger.debug("Pixel diff failed: %s", exc)
        return 0.0


def _vision_verify(action_description: str, after_b64: str) -> Optional[bool]:
    prompt = (
        f"I just {action_description}. Did this action succeed on the screen? "
        f"Answer only 'yes' or 'no' followed by a brief reason."
    )
    try:
        import base64
        answer = _ask_vision(prompt, after_b64)
        if answer:
            return answer.strip().lower().startswith("yes")
    except Exception as exc:
        logger.debug("Vision verify failed: %s", exc)
    return None


def verify(action: str, result_action: str, before_b64: str, after_b64: str, action_success: bool) -> tuple[bool, str]:
    if result_action in ("done", "fail", "wait", "zoom"):
        return True, f"Action type '{result_action}' needs no verification"

    if not after_b64:
        return action_success, "No after-screenshot available"

    time.sleep(_VERIFY_WAIT_SECONDS)

    diff = _pixel_diff(before_b64, after_b64)
    pixel_changed = diff > _PIXEL_DIFF_THRESHOLD

    vision_ok = _vision_verify(f"{action} \"{result_action}\"", after_b64)

    if vision_ok is True:
        return True, f"Vision confirmed success, pixel diff {diff:.1%}"
    if vision_ok is False:
        logger.warning("Vision reported failure for %s", result_action)
        return False, f"Vision reported action failed, pixel diff {diff:.1%}"

    if pixel_changed:
        return True, f"Pixel diff {diff:.1%} suggests visible change"
    if action_success:
        return True, f"Action reported success, pixel diff {diff:.1%}"

    return False, f"No visible change (pixel diff {diff:.1%}) and action reported failure"
