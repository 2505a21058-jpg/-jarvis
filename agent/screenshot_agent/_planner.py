"""
agent/screenshot_agent/_planner.py

Vision-based action planner. Takes the task, current ScreenRepr, and
action history, then asks a vision model to decide the next action.

Returns a PlannedAction with coordinates, text, or keys.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.screenshot_agent._perception import ScreenRepr

logger = logging.getLogger("jarvis.screenshot_agent.planner")

SUPPORTED_ACTIONS = {"click", "type", "key", "scroll", "wait", "zoom", "done", "fail"}

_ACTION_SCHEMA = """Return ONLY valid JSON, no other text. One of:
{"action":"click","x":int,"y":int}
{"action":"type","text":"..."}
{"action":"key","keys":"ctrl+s"}
{"action":"scroll","direction":"up|down","amount":int}
{"action":"wait","seconds":1}
{"action":"zoom","x1":int,"y1":int,"x2":int,"y2":int}
{"action":"done","reason":"..."}
{"action":"fail","reason":"..."}"""

_SYSTEM_PROMPT = """You are an AI assistant controlling this computer screen.
Your task is to choose the correct next action based on what you see.

Available actions:
- "click" [x,y]: Click at pixel coordinates. Use OCR positions below to find where elements are.
- "type": Type text at the current cursor position.
- "key": Send a keyboard shortcut like "ctrl+s", "alt+tab", "win+r".
- "scroll": Scroll the page up or down (amount = number of scroll clicks, positive = down).
- "wait": Pause briefly for a page to load or animation to finish.
- "zoom" [x1,y1,x2,y2]: You cannot read something clearly. Request a zoomed view of this region.
- "done": The task is complete.
- "fail": You cannot complete this task.

CRITICAL: Coordinates must be within the screen bounds of {width}x{height}px.
When you see OCR text like "Submit" at (520, 440), the center of that element
is at approximately x=520, y=440."""


@dataclass
class PlannedAction:
    action: str = "wait"
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    keys: Optional[str] = None
    direction: Optional[str] = None
    amount: int = 1
    seconds: float = 1.0
    x1: Optional[int] = None
    y1: Optional[int] = None
    x2: Optional[int] = None
    y2: Optional[int] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"action": self.action}
        if self.x is not None:
            d["x"] = self.x
        if self.y is not None:
            d["y"] = self.y
        if self.text is not None:
            d["text"] = self.text
        if self.keys is not None:
            d["keys"] = self.keys
        if self.direction is not None:
            d["direction"] = self.direction
        if self.amount != 1:
            d["amount"] = self.amount
        if self.seconds != 1.0:
            d["seconds"] = self.seconds
        if self.x1 is not None:
            d["x1"] = self.x1
        if self.y1 is not None:
            d["y1"] = self.y1
        if self.x2 is not None:
            d["x2"] = self.x2
        if self.y2 is not None:
            d["y2"] = self.y2
        if self.reason is not None:
            d["reason"] = self.reason
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PlannedAction:
        action = str(d.get("action", "wait")).lower()
        if action not in SUPPORTED_ACTIONS:
            action = "wait"
        return cls(
            action=action,
            x=_int_or_none(d.get("x")),
            y=_int_or_none(d.get("y")),
            text=d.get("text"),
            keys=d.get("keys"),
            direction=d.get("direction"),
            amount=int(d.get("amount", 1)),
            seconds=float(d.get("seconds", 1.0)),
            x1=_int_or_none(d.get("x1")),
            y1=_int_or_none(d.get("y1")),
            x2=_int_or_none(d.get("x2")),
            y2=_int_or_none(d.get("y2")),
            reason=d.get("reason"),
        )


def _int_or_none(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _format_ocr(repr: ScreenRepr) -> str:
    if not repr.ocr_texts:
        return "  (no text detected)"
    lines = []
    for t in repr.ocr_texts:
        lines.append(f'  - "{t.text}" at center ({t.x}, {t.y}) size {t.w}x{t.h} conf={t.confidence:.2f}')
    return "\n".join(lines[:60])


def _format_history(history: list[dict]) -> str:
    if not history:
        return "  (none yet)"
    lines = []
    for h in history[-8:]:
        action = h.get("action", "?")
        ok = "✓" if h.get("success") else "✗"
        msg = (h.get("message") or h.get("reason") or "")[:80]
        lines.append(f"  {ok} {action}: {msg}")
    return "\n".join(lines)


def _call_vision_planner(prompt: str, screenshot_b64: str) -> Optional[dict]:
    try:
        from models.gemma import call_gemma_vision_json
        result = call_gemma_vision_json(prompt=prompt, image_b64=screenshot_b64, system="")
        if isinstance(result, dict) and result.get("action"):
            return result
    except Exception as exc:
        logger.debug("Gemma vision planner failed: %s", exc)

    try:
        import requests
        from config import OLLAMA_GENERATE_URL, VISION_MODEL, VISION_REQUEST_TIMEOUT_SECONDS
        resp = requests.post(
            OLLAMA_GENERATE_URL,
            json={"model": VISION_MODEL, "prompt": prompt, "images": [screenshot_b64], "stream": False},
            timeout=VISION_REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            text = resp.json().get("response", "").strip()
            parsed = _extract_json(text)
            if parsed and parsed.get("action"):
                return parsed
    except Exception as exc:
        logger.debug("Ollama vision planner failed: %s", exc)

    return None


def _call_text_planner(prompt: str) -> Optional[dict]:
    try:
        from models.llm import call_llm_json
        return call_llm_json(system=_SYSTEM_PROMPT, user=prompt, temperature=0.1, max_tokens=200)
    except Exception as exc:
        logger.debug("LLM text planner failed: %s", exc)
    return None


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def plan(task: str, repr: ScreenRepr, history: list[dict]) -> PlannedAction:
    zoom_context = ""
    if repr.zoom_region:
        x1, y1, x2, y2 = repr.zoom_region
        zoom_context = f"\n[This view is ZOOMED into region ({x1},{y1})-({x2},{y2}) of the full screen.]"

    system = _SYSTEM_PROMPT.format(width=repr.width, height=repr.height)
    user = (
        f"TASK: {task}\n\n"
        f"SCREEN DESCRIPTION: {repr.vision_description}\n\n"
        f"TEXT FOUND ON SCREEN (with pixel positions):\n{_format_ocr(repr)}\n"
        f"{zoom_context}\n\n"
        f"PREVIOUS ACTIONS:\n{_format_history(history)}\n\n"
        f"{_ACTION_SCHEMA}"
    )

    prompt = f"{system}\n\n{user}"

    result = _call_vision_planner(prompt, repr.screenshot_b64)
    if result:
        logger.debug("Planner decided via vision: %s", result.get("action"))
        return PlannedAction.from_dict(result)

    result = _call_text_planner(user)
    if result:
        logger.debug("Planner decided via text: %s", result.get("action"))
        return PlannedAction.from_dict(result)

    logger.warning("All planners failed, defaulting to wait")
    return PlannedAction(action="wait", seconds=2.0, reason="planner unavailable")
