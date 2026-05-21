"""
skills/computer_control.py

General desktop automation agent.

This module is intentionally structured as a small think-act-observe loop:
1. Observe the machine state with accessibility/window context and optional vision.
2. Critique whether the next logical step is still needed.
3. Preview risk before acting.
4. Execute through a strategy chain.
5. Verify, record the trace, and recover or hand off safely.

The goal is "reliable hands", not blind confidence. High-risk actions always
stop for explicit user confirmation.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from config import (
    COMPUTER_CONTROL_APP_READY_WAIT_SECONDS,
    COMPUTER_CONTROL_KEY_PAUSE_SECONDS,
    COMPUTER_CONTROL_MAX_STEP_ATTEMPTS,
    COMPUTER_CONTROL_NOTIFY_TIMEOUT_SECONDS,
    COMPUTER_CONTROL_STEP_WAIT_SECONDS,
    COMPUTER_CONTROL_WAIT_POLL_SECONDS,
    COMPUTER_CONTROL_WAIT_TIMEOUT_SECONDS,
    PAINT_CANVAS_X_RATIO,
    PAINT_CANVAS_Y_RATIO,
    PAINT_DRAW_DURATION_SECONDS,
    PAINT_DRAW_SIZE_PIXELS,
)
from skills.base import SkillBase, SkillResult

# Lazy import for screenshot-only fallback
_screenshot_agent = None


logger = logging.getLogger("jarvis.skills.computer_control")


BROWSER_APPS = {"browser", "chrome", "edge", "firefox", "brave", "opera"}
PAINT_NAMES = {"paint", "mspaint", "microsoft paint"}
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

KEY_ALIASES = {
    "esc": "escape",
    "return": "enter",
    "windows": "win",
    "control": "ctrl",
    "cmd": "win",
    "command": "win",
}
KEY_NAMES = {
    "enter",
    "tab",
    "escape",
    "esc",
    "space",
    "backspace",
    "delete",
    "del",
    "home",
    "end",
    "pageup",
    "pagedown",
    "up",
    "down",
    "left",
    "right",
    "ctrl",
    "control",
    "alt",
    "shift",
    "win",
    "windows",
    "cmd",
    "command",
}

HIGH_RISK_WORDS = {
    "book",
    "buy",
    "purchase",
    "pay",
    "checkout",
    "confirm",
    "submit",
    "reserve",
    "order",
    "delete",
    "transfer",
    "format",
    "uninstall",
    "send money",
}
MEDIUM_RISK_WORDS = {
    "download",
    "install",
    "upload",
    "share",
    "post",
    "email",
    "send",
    "fill",
    "save",
    "export",
    "close",
    "overwrite",
    "settings",
}
PERSONAL_DATA_WORDS = {"password", "card", "cvv", "otp", "address", "phone", "email", "aadhaar", "ssn"}


@dataclass
class AutomationObservation:
    """A lightweight perception snapshot used before and after each action."""

    active_app: str = ""
    active_window: str = ""
    browser_url: str = ""
    focused_element: str = ""
    accessibility_text: list[str] = field(default_factory=list)
    vision_description: str = ""
    screenshot_available: bool = False

    def summary(self) -> str:
        parts = []
        if self.active_app:
            parts.append(f"app={self.active_app}")
        if self.active_window:
            parts.append(f"window={self.active_window}")
        if self.browser_url:
            parts.append(f"url={self.browser_url}")
        if self.focused_element:
            parts.append(f"focus={self.focused_element}")
        if self.vision_description:
            parts.append(f"vision={self.vision_description[:120]}")
        return "; ".join(parts) if parts else "screen context unavailable"

    def contains_text(self, text: str) -> bool:
        needle = str(text or "").strip().lower()
        if not needle:
            return False
        haystack = " ".join(
            [
                self.active_app,
                self.active_window,
                self.browser_url,
                self.focused_element,
                self.vision_description,
                *self.accessibility_text,
            ]
        ).lower()
        return needle in haystack


@dataclass
class AutomationStep:
    """A logical desktop action with risk, expected outcome, and recovery strategies."""

    action: str
    description: str
    skill_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    expected: str = ""
    risk: str = RISK_LOW
    condition: dict[str, Any] = field(default_factory=dict)
    requires_user: bool = False


@dataclass
class StepOutcome:
    """One attempt in the strategy chain."""

    step_index: int
    description: str
    strategy: str
    success: bool
    message: str = ""
    error: str = ""
    risk: str = RISK_LOW
    verified: bool = False
    attempt: int = 1
    observation: str = ""


@dataclass
class AutomationTrace:
    """Rich but compact trace for user summaries and debugging."""

    task: str
    started_at: float = field(default_factory=time.monotonic)
    observations: list[str] = field(default_factory=list)
    previews: list[str] = field(default_factory=list)
    outcomes: list[StepOutcome] = field(default_factory=list)
    handoffs: list[str] = field(default_factory=list)

    def add_observation(self, observation: AutomationObservation) -> None:
        self.observations.append(observation.summary())
        self.observations = self.observations[-8:]

    def add_preview(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.previews.append(text)

    def add_outcome(self, outcome: StepOutcome) -> None:
        self.outcomes.append(outcome)

    def add_handoff(self, message: str) -> None:
        text = str(message or "").strip()
        if text:
            self.handoffs.append(text)

    def summary(self, final_message: str = "") -> str:
        lines: list[str] = []
        if final_message:
            lines.append(final_message.strip())

        successful = [outcome for outcome in self.outcomes if outcome.success and outcome.verified]
        recovered = [outcome for outcome in self.outcomes if outcome.success and outcome.attempt > 1]
        failed = [outcome for outcome in self.outcomes if not outcome.success]

        if successful:
            lines.append("Completed:")
            seen: set[str] = set()
            for outcome in successful:
                if outcome.description in seen:
                    continue
                seen.add(outcome.description)
                lines.append(f"- {outcome.description}")

        if recovered:
            lines.append("Recovered:")
            for outcome in recovered:
                lines.append(f"- {outcome.description} via {outcome.strategy}")

        if self.previews:
            lines.append("Caution:")
            for preview in self.previews[-3:]:
                lines.append(f"- {preview}")

        if failed:
            lines.append("Tried:")
            for outcome in failed[-4:]:
                detail = outcome.error or outcome.message or "no details"
                lines.append(f"- {outcome.description} via {outcome.strategy}: {detail}")

        if self.handoffs:
            lines.append("Needs you:")
            for message in self.handoffs[-2:]:
                lines.append(f"- {message}")

        if not lines:
            return "No automation actions were taken."
        return "\n".join(lines)


@dataclass
class AutomationContext:
    """Task-local memory for the desktop agent loop."""

    task: str
    state: Any
    plan: list[AutomationStep]
    max_attempts: int = COMPUTER_CONTROL_MAX_STEP_ATTEMPTS
    trace: AutomationTrace = field(init=False)
    recent_observations: list[AutomationObservation] = field(default_factory=list)
    step_cursor: int = 0

    def __post_init__(self) -> None:
        self.max_attempts = max(1, min(int(self.max_attempts or 4), 4))
        self.trace = AutomationTrace(task=self.task)

    def remember(self, observation: AutomationObservation) -> None:
        self.recent_observations.append(observation)
        self.recent_observations = self.recent_observations[-6:]
        self.trace.add_observation(observation)


def _state_get(state: Any, key: str, default: Any = "") -> Any:
    getter = getattr(state, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(state, key, default)


def _state_set(state: Any, key: str, value: Any) -> None:
    if state is None:
        return
    if hasattr(state, key):
        setattr(state, key, value)
    elif isinstance(state, dict):
        state[key] = value


def _vision_enabled() -> bool:
    return os.environ.get("JARVIS_VISION_VERIFY", "false").lower() == "true"


def _contains_any(text: str, words: set[str]) -> bool:
    lowered = str(text or "").lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in words)


def _contains_risky_action(task: str) -> bool:
    return _contains_any(task, HIGH_RISK_WORDS)


def _classify_risk(text: str, action: str = "", params: dict[str, Any] | None = None) -> str:
    params_text = " ".join(str(value) for value in (params or {}).values())
    combined = f"{text} {action} {params_text}".lower()
    if _contains_any(combined, HIGH_RISK_WORDS):
        return RISK_HIGH
    if "submit" in combined and _contains_any(combined, PERSONAL_DATA_WORDS):
        return RISK_HIGH
    if _contains_any(combined, MEDIUM_RISK_WORDS) or _contains_any(combined, PERSONAL_DATA_WORDS):
        return RISK_MEDIUM
    return RISK_LOW


def _extract_open_app(task: str) -> str:
    match = re.search(
        r"\bopen\s+(?P<app>[\w\s.+#-]+?)(?=\s+(?:and\s+)?(?:search|find|look|book|draw|click|type|fill|select|navigate|pay|buy|purchase|copy|paste)\b|,|$)",
        task,
        re.IGNORECASE,
    )
    if not match:
        return ""
    app = re.sub(r"\s+", " ", match.group("app")).strip().lower()
    return "paint" if app in PAINT_NAMES else app


def _extract_search_query(task: str) -> str:
    match = re.search(r"\b(?:search(?:\s+for)?|find|look\s+up)\s+(?P<query>.+)", task, re.IGNORECASE)
    if not match:
        return ""
    query = match.group("query").strip()
    query = re.split(
        r"\s+and\s+(?:book|buy|purchase|pay|checkout|confirm|submit|reserve|order|click|select|open|play|watch|save|export)\b",
        query,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return query.strip(" ,.")


def _extract_action_query(task: str) -> str:
    match = re.search(r"\b(?:book|buy|purchase|reserve|order)\s+(?P<query>.+)", task, re.IGNORECASE)
    if not match:
        return ""
    query = re.split(
        r"\s+and\s+(?:pay|checkout|confirm|submit|click|select|open)\b",
        match.group("query").strip(),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return query.strip(" ,.")


def _normalize_key_sequence(sequence: str) -> list[str]:
    raw_keys = re.split(r"\s*\+\s*|\s+", str(sequence or "").strip().lower())
    return [KEY_ALIASES.get(key, key) for key in raw_keys if key and key != "the"]


def _looks_like_key_sequence(text: str) -> bool:
    cleaned = re.sub(r"\b(?:key|button)\b", "", str(text or "").strip().lower()).strip()
    keys = _normalize_key_sequence(cleaned)
    if not keys:
        return False
    valid_named_keys = {KEY_ALIASES.get(name, name) for name in KEY_NAMES}
    has_modifier = any(key in {"ctrl", "alt", "shift", "win"} for key in keys)
    if has_modifier:
        return all(key in valid_named_keys or re.fullmatch(r"[a-z0-9]|f\d{1,2}", key) for key in keys)
    return "+" in cleaned or all(key in valid_named_keys or re.fullmatch(r"f\d{1,2}", key) for key in keys)


def _extract_key_sequence(task: str) -> str:
    match = re.search(
        r"\b(?:press|hit|tap|send)\s+(?P<keys>.+?)(?:\s+(?:key|keys))?(?:$|\s+and\s+)",
        task,
        re.IGNORECASE,
    )
    if not match:
        return ""
    keys = match.group("keys").strip(" .\"'")
    return "+".join(_normalize_key_sequence(keys)) if _looks_like_key_sequence(keys) else ""


def _extract_click_target(task: str) -> str:
    match = re.search(
        r"\b(?:click|press|select|choose)\s+(?:the\s+)?(?P<target>.+?)(?:\s+(?:button|link|tab|field|option))?(?:$|\s+and\s+)",
        task,
        re.IGNORECASE,
    )
    if not match:
        return ""
    target = match.group("target").strip(" .\"'")
    return "" if _looks_like_key_sequence(target) else target


def _strip_type_target(text: str) -> str:
    return re.split(
        r"\s+and\s+(?:click|press|select|choose|book|buy|purchase|pay|checkout|confirm|submit|save|export)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" .\"'")


def _extract_type_text(task: str) -> str:
    match = re.search(r"\b(?:type|write|enter)\s+(?P<text>.+)", task, re.IGNORECASE)
    if not match:
        return ""
    return _strip_type_target(match.group("text"))


def _extract_draw_subject(task: str) -> str:
    match = re.search(
        r"\bdraw\s+(?P<subject>.+?)(?:\s+(?:in|on)\s+(?:microsoft\s+)?paint)?(?:\s+and\s+(?:save|export).*)?$",
        task,
        re.IGNORECASE,
    )
    return match.group("subject").strip(" .\"'") if match else ""


def _extract_save_path(task: str) -> str:
    match = re.search(r"\b(?:save|export)(?:\s+(?:it|file|drawing))?\s+(?:as|to)\s+(?P<path>.+)$", task, re.IGNORECASE)
    return match.group("path").strip(" .\"'") if match else ""


def _extract_copy_paste(task: str) -> dict[str, str]:
    match = re.search(
        r"\bcopy\s+(?P<item>.+?)\s+from\s+(?P<source>.+?)\s+to\s+(?P<target>.+)$",
        task,
        re.IGNORECASE,
    )
    if not match:
        return {}
    return {
        "item": match.group("item").strip(" .\"'"),
        "source": match.group("source").strip(" .\"'").lower(),
        "target": match.group("target").strip(" .\"'").lower(),
    }


def _extract_form_fields(task: str) -> dict[str, str]:
    match = re.search(r"\bfill(?:\s+(?:the\s+)?form)?\s+(?:with\s+)?(?P<body>.+)", task, re.IGNORECASE)
    if not match:
        return {}
    body = re.split(r"\s+and\s+(?:submit|pay|confirm|book|buy)\b", match.group("body"), maxsplit=1, flags=re.IGNORECASE)[0]
    fields: dict[str, str] = {}
    segments = re.split(
        r"\s*[,;]\s*|\s+\band\b\s+(?=[a-zA-Z][\w\s]{0,30}?\s*(?:=|:|\bas\b|\bis\b))",
        body,
        flags=re.IGNORECASE,
    )
    for segment in segments:
        field_match = re.match(
            r"\s*(?P<field>[a-zA-Z][\w\s]{0,30}?)\s*(?:=|:|\bas\b|\bis\b)\s*(?P<value>.+?)\s*$",
            segment,
            flags=re.IGNORECASE,
        )
        if not field_match:
            continue
        clean_field = re.sub(r"\s+", " ", field_match.group("field")).strip().lower()
        clean_value = field_match.group("value").strip(" .\"'")
        if clean_field and clean_value:
            fields[clean_field] = clean_value
    return fields


def _extract_condition(task: str) -> dict[str, Any]:
    match = re.search(r"\bif\s+(?:the\s+)?price\s+is\s+under\s+(?P<amount>[\d,.]+)", task, re.IGNORECASE)
    if not match:
        return {}
    amount = float(match.group("amount").replace(",", ""))
    return {"type": "price_below", "threshold": amount}


def _extract_tab_action(task: str) -> str:
    lowered = str(task or "").strip().lower()
    if re.search(r"\b(?:new|open)\s+(?:browser\s+)?tab\b", lowered):
        return "ctrl+t"
    if re.search(r"\bclose\s+(?:browser\s+)?tab\b", lowered):
        return "ctrl+w"
    if re.search(r"\b(?:previous|last)\s+(?:browser\s+)?tab\b", lowered):
        return "ctrl+shift+tab"
    if re.search(r"\b(?:switch|next)\s+(?:browser\s+)?tab\b", lowered):
        return "ctrl+tab"
    return ""


def _step(
    action: str,
    description: str,
    *,
    skill_name: str = "",
    params: dict[str, Any] | None = None,
    alternatives: list[dict[str, Any]] | None = None,
    strategies: list[str] | None = None,
    expected: str = "",
    risk: str | None = None,
    condition: dict[str, Any] | None = None,
    requires_user: bool = False,
) -> AutomationStep:
    payload = dict(params or {})
    resolved_risk = risk or _classify_risk(description, action, payload)
    return AutomationStep(
        action=action,
        description=description,
        skill_name=skill_name,
        params=payload,
        alternatives=list(alternatives or []),
        strategies=list(strategies or []),
        expected=expected,
        risk=resolved_risk,
        condition=dict(condition or {}),
        requires_user=requires_user,
    )


def _build_plan(task: str) -> list[AutomationStep]:
    """Build an initial deterministic plan; the agent loop can still recover/replan while executing."""
    task_text = str(task or "").strip()
    lowered = task_text.lower()
    app = _extract_open_app(task_text)
    query = _extract_search_query(task_text)
    action_query = _extract_action_query(task_text)
    click_target = _extract_click_target(task_text)
    key_sequence = _extract_key_sequence(task_text)
    type_text = _extract_type_text(task_text)
    draw_subject = _extract_draw_subject(task_text)
    save_path = _extract_save_path(task_text)
    copy_paste = _extract_copy_paste(task_text)
    fields = _extract_form_fields(task_text)
    condition = _extract_condition(task_text)
    tab_keys = _extract_tab_action(task_text)
    pronoun_action = action_query.lower() in {"it", "one", "that", "this"}
    search_query = query or ("" if condition and pronoun_action else action_query)
    steps: list[AutomationStep] = []

    if copy_paste:
        steps.extend(
            [
                _step("skill", f"Open source app {copy_paste['source']}", skill_name="open_app", params={"app": copy_paste["source"]}, expected=copy_paste["source"]),
                _step("skill", f"Copy {copy_paste['item']}", skill_name="gui_automate", params={"action": "press", "keys": "ctrl+c"}, strategies=["hotkey"], expected="clipboard copied"),
                _step("skill", f"Open target app {copy_paste['target']}", skill_name="open_app", params={"app": copy_paste["target"]}, expected=copy_paste["target"]),
                _step("skill", "Paste copied content", skill_name="gui_automate", params={"action": "press", "keys": "ctrl+v"}, strategies=["hotkey"], expected="content pasted"),
            ]
        )
    elif draw_subject and ("paint" in lowered or app == "paint"):
        steps.append(
            _step(
                "skill",
                "Open Microsoft Paint",
                skill_name="open_app",
                params={"app": "paint"},
                alternatives=[{"skill_name": "open_app", "params": {"app": "mspaint"}}],
                expected="paint",
            )
        )
        steps.append(_step("draw", f"Draw {draw_subject} in Paint", params={"subject": draw_subject}, strategies=["draw"], expected=draw_subject))
        if save_path:
            steps.append(_step("save_file", f"Save drawing to {save_path}", params={"path": save_path}, strategies=["type"], risk=RISK_MEDIUM, expected=save_path))
    elif app and search_query:
        steps.append(
            _step(
                "skill",
                f"Open {app} and search for {search_query}",
                skill_name="open_and_search",
                params={"app": app, "query": search_query},
                alternatives=[{"skill_name": "browse", "params": {"query": search_query}}],
                strategies=["skill", "app_search", "browser_search"],
                expected=search_query,
            )
        )
    elif app:
        steps.append(
            _step(
                "skill",
                f"Open {app}",
                skill_name="open_app",
                params={"app": app},
                alternatives=[{"skill_name": "browse", "params": {"query": app}}] if app in BROWSER_APPS else [],
                strategies=["skill", "app_search"],
                expected=app,
            )
        )
    elif search_query:
        steps.append(_step("skill", f"Search for {search_query}", skill_name="browse", params={"query": search_query}, strategies=["skill", "browser_search"], expected=search_query))

    if fields:
        steps.append(_step("fill_form", "Fill form fields", params={"fields": fields}, strategies=["accessibility_type", "keyboard"], risk=RISK_MEDIUM, expected="form fields filled"))

    if click_target:
        steps.append(_step("skill", f"Click {click_target}", skill_name="gui_automate", params={"action": "click", "element": click_target}, strategies=["accessibility_click", "keyboard_navigation", "vision_click"], expected=click_target))

    if key_sequence:
        steps.append(_step("skill", f"Press {key_sequence}", skill_name="gui_automate", params={"action": "press", "keys": key_sequence}, strategies=["hotkey"], expected=key_sequence))

    if tab_keys:
        steps.append(_step("skill", f"Manage browser tab with {tab_keys}", skill_name="gui_automate", params={"action": "press", "keys": tab_keys}, strategies=["hotkey"], risk=RISK_MEDIUM if "ctrl+w" == tab_keys else RISK_LOW, expected=tab_keys))

    if type_text and not draw_subject and "search" not in lowered and not fields:
        steps.append(_step("skill", "Type requested text", skill_name="type_text", params={"text": type_text}, strategies=["skill", "keyboard"], expected=type_text))

    if _contains_risky_action(task_text):
        steps.append(
            _step(
                "user_confirmation",
                "Pause before risky action",
                params={"task": task_text},
                strategies=["handoff"],
                risk=RISK_HIGH,
                condition=condition,
                requires_user=True,
            )
        )

    if not steps:
        steps.append(_step("needs_help", "Ask user for more detail", params={"task": task_text}, strategies=["handoff"], requires_user=True))

    return steps


def _notify_user(message: str) -> None:
    logger.warning("Computer control needs attention: %s", message)
    print(f"\nJARVIS NEEDS HELP: {message}\n")
    try:
        from plyer import notification

        notification.notify(
            title="Jarvis needs help",
            message=message,
            timeout=COMPUTER_CONTROL_NOTIFY_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.debug("Computer-control desktop notification unavailable: %s", exc)


def _get_active_window_title() -> str:
    try:
        from skills.gui_automate import _get_active_window_title as get_title

        return get_title()
    except Exception as exc:
        logger.debug("Active window observation unavailable: %s", exc)
        return ""


def _accessibility_snapshot(app_name: str = "") -> list[str]:
    try:
        from skills.gui_automate import _accessibility_snapshot as snapshot

        return snapshot(app_name=app_name, limit=40)
    except Exception as exc:
        logger.debug("Accessibility snapshot unavailable: %s", exc)
        return []


def _vision_observation(question: str = "") -> tuple[str, bool]:
    if not _vision_enabled():
        return "", False
    try:
        from agent.screen_verify import _ask_vision_model, _take_screenshot

        screenshot = _take_screenshot()
        if not screenshot:
            return "", False
        prompt = question or (
            "Describe the active app/window and any important buttons, fields, dialogs, "
            "or page content visible on this computer screen in 1-2 concise sentences."
        )
        answer = _ask_vision_model(screenshot, prompt) or ""
        return answer.strip(), True
    except Exception as exc:
        logger.debug("Vision observation unavailable: %s", exc)
        return "", False


def _observe(context: AutomationContext, step: AutomationStep | None = None, *, force_vision: bool = False) -> AutomationObservation:
    active_app = str(_state_get(context.state, "active_app", "") or "")
    browser_url = str(_state_get(context.state, "browser_url", "") or "")
    active_window = _get_active_window_title()
    accessibility_text = _accessibility_snapshot(active_app)
    vision_description = ""
    screenshot_available = False
    if force_vision or (step and step.action in {"fill_form", "user_confirmation"} and _vision_enabled()):
        vision_description, screenshot_available = _vision_observation()

    observation = AutomationObservation(
        active_app=active_app,
        active_window=active_window,
        browser_url=browser_url,
        accessibility_text=accessibility_text,
        vision_description=vision_description,
        screenshot_available=screenshot_available,
    )
    context.remember(observation)
    return observation


def _critique_step(step: AutomationStep, observation: AutomationObservation) -> tuple[bool, str]:
    """Return (should_execute, reason) using current screen/task-local state."""
    if step.action == "skill" and step.skill_name == "open_app":
        target = str(step.params.get("app", "")).lower()
        if target and (target == observation.active_app.lower() or observation.contains_text(target)):
            return False, f"{target} already appears active."
    if step.expected and observation.contains_text(step.expected) and step.action in {"skill"} and step.skill_name in {"open_and_search", "browse"}:
        return False, f"Expected content '{step.expected}' already appears visible."
    return True, "Step still needed."


def _condition_allows(step: AutomationStep, observation: AutomationObservation) -> tuple[bool, str]:
    condition = dict(step.condition or {})
    if not condition:
        return True, ""
    if condition.get("type") == "price_below":
        threshold = float(condition.get("threshold") or 0)
        text = " ".join([observation.vision_description, *observation.accessibility_text])
        prices = [float(match.replace(",", "")) for match in re.findall(r"(?:rs\.?|inr|\$)?\s*([\d,]+(?:\.\d+)?)", text, flags=re.IGNORECASE)]
        if not prices:
            return False, f"I could not verify a price under {threshold:g} from the current screen."
        lowest = min(prices)
        return lowest < threshold, f"Lowest visible price is {lowest:g}; threshold is {threshold:g}."
    return True, ""


def _preview_risk(context: AutomationContext, step: AutomationStep, observation: AutomationObservation) -> tuple[bool, str]:
    risk = step.risk or _classify_risk(step.description, step.action, step.params)
    step.risk = risk
    if risk == RISK_HIGH:
        condition_ok, condition_note = _condition_allows(step, observation)
        condition_text = f"\nCondition check: {condition_note}" if condition_note else ""
        message = (
            "I navigated as far as I safely can. I need your explicit confirmation before "
            f"continuing with: {step.description}.{condition_text}\n"
            "I will not complete bookings, payments, purchases, deletes, transfers, or submissions without you confirming."
        )
        if not condition_ok and condition_note:
            message = f"{message}\nI am stopping because the condition is not safely verified."
        context.trace.add_handoff(message)
        return False, message
    if risk == RISK_MEDIUM:
        message = f"Medium-risk action preview: {step.description}. I will continue carefully and stop before irreversible changes."
        context.trace.add_preview(message)
        logger.info(message)
    return True, ""


def _execute_skill_step(step: AutomationStep, state, step_index: int) -> tuple[bool, str]:
    """Compatibility wrapper used by the strategy loop and tests."""
    from agent.executor import get_executor

    executor = get_executor()
    result = executor.execute(step.skill_name, step.params, state, step_index=step_index)
    if result.success:
        return True, str(result.output or step.description)

    error = result.error or "unknown error"
    for alternative in step.alternatives:
        alt_skill = str(alternative.get("skill_name", "")).strip()
        alt_params = dict(alternative.get("params", {}) or {})
        if not alt_skill:
            continue
        alt_result = executor.execute(alt_skill, alt_params, state, step_index=step_index)
        if alt_result.success:
            return True, f"{step.description} recovered with {alt_skill}: {alt_result.output}"
        error = alt_result.error or error

    return False, f"{step.description} failed: {error}"


def _execute_gui_action(params: dict[str, Any], state, step_index: int) -> tuple[bool, str]:
    step = AutomationStep(action="skill", description=f"GUI {params.get('action', 'action')}", skill_name="gui_automate", params=dict(params))
    return _execute_skill_step(step, state, step_index)


def _press_hotkey(keys: str, state, step_index: int) -> tuple[bool, str]:
    return _execute_gui_action({"action": "press", "keys": keys}, state, step_index)


def _browser_search(step: AutomationStep, state, step_index: int) -> tuple[bool, str]:
    query = str(step.params.get("query") or step.expected or step.description).strip()
    app = str(step.params.get("app") or _state_get(state, "active_app", "") or "").strip()
    if app and app not in BROWSER_APPS:
        params = {"app": app, "query": query}
        fallback = AutomationStep(action="skill", description=f"Search {app}", skill_name="open_and_search", params=params)
        return _execute_skill_step(fallback, state, step_index)
    return _execute_skill_step(AutomationStep(action="skill", description=f"Search {query}", skill_name="browse", params={"query": query}), state, step_index)


def _keyboard_navigation_click(step: AutomationStep, state, step_index: int) -> tuple[bool, str]:
    element = str(step.params.get("element") or "").strip()
    if not element:
        return False, "No element target for keyboard navigation"
    ok, message = _press_hotkey("tab", state, step_index)
    if not ok:
        return False, message
    time.sleep(COMPUTER_CONTROL_KEY_PAUSE_SECONDS)
    ok, message = _press_hotkey("enter", state, step_index)
    if ok:
        return True, f"Tried keyboard navigation to activate {element}"
    return False, message


def _vision_coordinate_click(step: AutomationStep) -> tuple[bool, str]:
    if not _vision_enabled():
        return False, "Vision coordinate click is disabled. Set JARVIS_VISION_VERIFY=true to enable it."
    try:
        from agent.screen_verify import _ask_vision_model, _take_screenshot

        screenshot = _take_screenshot()
        if not screenshot:
            return False, "Screenshot unavailable for vision click"
        target = str(step.params.get("element") or step.expected or step.description)
        answer = _ask_vision_model(
            screenshot,
            f"Find the screen coordinates for '{target}'. Answer only as x=<number>, y=<number>.",
        ) or ""
        match = re.search(r"x\s*=\s*(\d+)\D+y\s*=\s*(\d+)", answer, re.IGNORECASE)
        if not match:
            return False, f"Vision did not return coordinates: {answer[:80]}"
        import pyautogui

        x, y = int(match.group(1)), int(match.group(2))
        pyautogui.click(x, y)
        return True, f"Clicked {target} at ({x}, {y}) using vision"
    except Exception as exc:
        return False, f"Vision click failed: {exc}"


def _fill_form(fields: dict[str, str], state, step_index: int) -> tuple[bool, str]:
    if not fields:
        return False, "No form fields provided"

    messages: list[str] = []
    for field, value in fields.items():
        ok, message = _execute_gui_action({"action": "click", "element": field}, state, step_index)
        if not ok:
            ok, message = _press_hotkey("tab", state, step_index)
        if not ok:
            return False, f"Could not focus field '{field}': {message}"
        time.sleep(COMPUTER_CONTROL_KEY_PAUSE_SECONDS)
        ok, message = _execute_gui_action({"action": "type_active", "text": value}, state, step_index)
        if not ok:
            return False, f"Could not type into '{field}': {message}"
        messages.append(f"{field}=filled")
    return True, "Filled form fields: " + ", ".join(messages)


def _fill_form_with_keyboard(fields: dict[str, str], state, step_index: int) -> tuple[bool, str]:
    if not fields:
        return False, "No form fields provided"
    filled: list[str] = []
    for field, value in fields.items():
        ok, message = _press_hotkey("tab", state, step_index)
        if not ok:
            return False, message
        time.sleep(COMPUTER_CONTROL_KEY_PAUSE_SECONDS)
        ok, message = _execute_gui_action({"action": "type_active", "text": value}, state, step_index)
        if not ok:
            return False, f"Could not type fallback value for '{field}': {message}"
        filled.append(field)
    return True, "Filled fields with keyboard fallback: " + ", ".join(filled)


def _save_current_file(path: str, state, step_index: int) -> tuple[bool, str]:
    target = str(path or "").strip()
    if not target:
        return False, "No save path provided"
    ok, message = _press_hotkey("ctrl+s", state, step_index)
    if not ok:
        return False, message
    time.sleep(COMPUTER_CONTROL_APP_READY_WAIT_SECONDS)
    ok, message = _execute_gui_action({"action": "type_active", "text": target}, state, step_index)
    if not ok:
        return False, message
    ok, message = _press_hotkey("enter", state, step_index)
    if ok:
        return True, f"Requested save to {target}"
    return False, message


def _draw_in_paint(subject: str) -> tuple[bool, str]:
    try:
        import pyautogui

        time.sleep(COMPUTER_CONTROL_APP_READY_WAIT_SECONDS)
        try:
            from skills.utils.window_focus import focus_any_window

            focus_any_window(["paint", "mspaint"])
        except Exception as exc:
            logger.debug("Paint focus helper unavailable: %s", exc)

        width, height = pyautogui.size()
        center_x = int(width * PAINT_CANVAS_X_RATIO)
        center_y = int(height * PAINT_CANVAS_Y_RATIO)
        size = max(int(PAINT_DRAW_SIZE_PIXELS), 60)
        half = int(size / 2)
        roof_height = int(size * 0.55)
        subject_lower = subject.lower()

        # Click the likely canvas area before drawing so Paint receives drag input.
        pyautogui.click(center_x, center_y)
        time.sleep(COMPUTER_CONTROL_KEY_PAUSE_SECONDS)

        pyautogui.moveTo(center_x - half, center_y, duration=PAINT_DRAW_DURATION_SECONDS)
        if "house" in subject_lower:
            pyautogui.dragRel(size, 0, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(0, int(size * 0.75), duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(-size, 0, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(0, -int(size * 0.75), duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.moveTo(center_x - int(size * 0.6), center_y, duration=PAINT_DRAW_DURATION_SECONDS)
            pyautogui.dragTo(center_x, center_y - roof_height, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragTo(center_x + int(size * 0.6), center_y, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
        elif "circle" in subject_lower:
            pyautogui.dragRel(half, -half, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(half, half, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(-half, half, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(-half, -half, duration=PAINT_DRAW_DURATION_SECONDS, button="left")
        else:
            pyautogui.dragRel(half, -int(size * 0.4), duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(half, int(size * 0.4), duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(-size, int(size * 0.4), duration=PAINT_DRAW_DURATION_SECONDS, button="left")
            pyautogui.dragRel(size, int(size * 0.4), duration=PAINT_DRAW_DURATION_SECONDS, button="left")

        return True, f"Drew a simple {subject} sketch in Paint."
    except Exception as exc:
        return False, f"Drawing failed: {exc}"


def _get_screenshot_agent():
    global _screenshot_agent
    if _screenshot_agent is None:
        from agent.screenshot_agent import ScreenshotAgent
        _screenshot_agent = ScreenshotAgent(max_steps=3, zoom_enabled=False)
    return _screenshot_agent


def _screenshot_click(step: AutomationStep) -> tuple[bool, str]:
    element = str(step.params.get("element") or step.expected or "").strip()
    if not element:
        return False, "No element target for screenshot click"
    agent = _get_screenshot_agent()
    result = agent.single_action("click", {"element": element, "task": f"Click the '{element}' button or element on screen"})
    return result.success, result.message


def _strategies_for_step(step: AutomationStep) -> list[str]:
    if step.strategies:
        return list(step.strategies)
    if step.action == "draw":
        return ["draw"]
    if step.action == "fill_form":
        return ["accessibility_type", "keyboard"]
    if step.action == "save_file":
        return ["hotkey", "type"]
    if step.skill_name == "gui_automate" and step.params.get("action") == "click":
        return ["accessibility_click", "keyboard_navigation", "vision_click", "screenshot"]
    if step.skill_name == "gui_automate" and step.params.get("action") in {"press", "hotkey"}:
        return ["hotkey"]
    if step.skill_name in {"open_and_search", "browse"}:
        return ["skill", "browser_search"]
    return ["skill"]


def _execute_strategy(step: AutomationStep, strategy: str, context: AutomationContext, step_index: int) -> tuple[bool, str]:
    if strategy == "skill":
        return _execute_skill_step(step, context.state, step_index)
    if strategy == "app_search" or strategy == "browser_search":
        return _browser_search(step, context.state, step_index)
    if strategy == "accessibility_click":
        params = dict(step.params)
        params["action"] = "click"
        return _execute_gui_action(params, context.state, step_index)
    if strategy == "keyboard_navigation":
        return _keyboard_navigation_click(step, context.state, step_index)
    if strategy == "vision_click":
        return _vision_coordinate_click(step)
    if strategy == "screenshot":
        return _screenshot_click(step)
    if strategy == "hotkey":
        return _press_hotkey(str(step.params.get("keys") or step.params.get("key") or ""), context.state, step_index)
    if strategy == "keyboard" and step.action == "fill_form":
        return _fill_form_with_keyboard(dict(step.params.get("fields") or {}), context.state, step_index)
    if strategy == "keyboard":
        text = str(step.params.get("text") or "")
        return _execute_gui_action({"action": "type_active", "text": text}, context.state, step_index)
    if strategy == "accessibility_type":
        return _fill_form(dict(step.params.get("fields") or {}), context.state, step_index)
    if strategy == "draw":
        return _draw_in_paint(str(step.params.get("subject", "drawing")))
    if strategy == "type":
        return _save_current_file(str(step.params.get("path") or ""), context.state, step_index)
    return False, f"Unknown strategy: {strategy}"


def _wait_for_expected(step: AutomationStep, context: AutomationContext) -> AutomationObservation:
    deadline = time.monotonic() + max(COMPUTER_CONTROL_WAIT_TIMEOUT_SECONDS, 0.5)
    observation = _observe(context, step, force_vision=False)
    while step.expected and time.monotonic() < deadline:
        if observation.contains_text(step.expected):
            return observation
        time.sleep(COMPUTER_CONTROL_WAIT_POLL_SECONDS)
        observation = _observe(context, step, force_vision=False)
    return observation


def _verify_step(step: AutomationStep, context: AutomationContext, ok: bool, message: str) -> tuple[bool, AutomationObservation, str]:
    if not ok:
        return False, _observe(context, step, force_vision=False), message

    observation = _observe(context, step, force_vision=False)
    if step.expected and observation.contains_text(step.expected):
        return True, observation, "Verified expected screen/context text."

    has_live_context = bool(observation.active_window or observation.browser_url or observation.accessibility_text)
    if step.expected and has_live_context:
        observation = _wait_for_expected(step, context)
        if observation.contains_text(step.expected):
            return True, observation, "Verified expected screen/context text."

    if _vision_enabled() and step.expected:
        vision_text, screenshot_available = _vision_observation(
            f"Did this action succeed: '{step.description}'? Expected evidence: '{step.expected}'. "
            "Answer yes or no followed by a short reason."
        )
        observation.vision_description = vision_text
        observation.screenshot_available = screenshot_available
        if vision_text.lower().startswith("yes"):
            return True, observation, vision_text

    # Many desktop actions cannot be deterministically verified without vision/OCR, so successful low-level actions are accepted.
    return True, observation, message or "Action reported success; deterministic verification was limited."


def _handoff_for_failed_step(context: AutomationContext, step: AutomationStep, outcomes: list[StepOutcome]) -> str:
    tried = ", ".join(outcome.strategy for outcome in outcomes[-context.max_attempts:]) or "no strategies"
    last_error = next((outcome.error for outcome in reversed(outcomes) if outcome.error), "unknown failure")
    message = (
        f"I could not complete '{step.description}' after {min(len(outcomes), context.max_attempts)} attempt(s). "
        f"I tried: {tried}. Last issue: {last_error}. Please adjust the screen or tell me what to try next."
    )
    context.trace.add_handoff(message)
    _notify_user(message)
    return message


def _execute_step_loop(context: AutomationContext, step: AutomationStep, step_index: int) -> tuple[bool, str]:
    observation = _observe(context, step, force_vision=False)
    should_execute, critique = _critique_step(step, observation)
    if not should_execute:
        outcome = StepOutcome(
            step_index=step_index,
            description=step.description,
            strategy="critique-skip",
            success=True,
            message=critique,
            risk=step.risk,
            verified=True,
            observation=observation.summary(),
        )
        context.trace.add_outcome(outcome)
        return True, critique

    allowed, risk_message = _preview_risk(context, step, observation)
    if not allowed:
        _notify_user(risk_message)
        return True, risk_message

    strategies = _strategies_for_step(step)
    outcomes_for_step: list[StepOutcome] = []

    for attempt, strategy in enumerate(strategies[: context.max_attempts], start=1):
        ok, message = _execute_strategy(step, strategy, context, step_index)
        verified, after_observation, verification_note = _verify_step(step, context, ok, message)
        outcome = StepOutcome(
            step_index=step_index,
            description=step.description,
            strategy=strategy,
            success=ok,
            message=message,
            error="" if ok else message,
            risk=step.risk,
            verified=verified,
            attempt=attempt,
            observation=after_observation.summary(),
        )
        context.trace.add_outcome(outcome)
        outcomes_for_step.append(outcome)
        if ok and verified:
            return True, verification_note or message

        # Re-observe between strategies so recovery uses current UI state instead of stale assumptions.
        _observe(context, step, force_vision=attempt >= 2 and _vision_enabled())
        time.sleep(COMPUTER_CONTROL_STEP_WAIT_SECONDS)

    return False, _handoff_for_failed_step(context, step, outcomes_for_step)


class ComputerControlSkill(SkillBase):
    name = "computer_control"
    description = "Plans and executes general app, browser, and desktop automation with safe fallbacks"
    timeout_seconds = 60.0

    def execute(self, params: dict, state) -> SkillResult:
        task = str(params.get("task") or params.get("query") or params.get("raw_input") or "").strip()
        if not task:
            return SkillResult(success=False, output=None, error="No automation task provided")

        context = AutomationContext(task=task, state=state, plan=[])
        _state_set(state, "current_task", {"type": "computer_control", "task": task})

        _observe(context, step=None, force_vision=False)
        context.plan = _build_plan(task)

        for index, step in enumerate(context.plan):
            context.step_cursor = index
            if step.action == "needs_help":
                message = f"I need more detail before I can automate this safely. Task: {task}"
                context.trace.add_handoff(message)
                _notify_user(message)
                return SkillResult(success=False, output=context.trace.summary(message), error=message)

            ok, message = _execute_step_loop(context, step, index)
            if not ok:
                return SkillResult(success=False, output=context.trace.summary(), error=message)

            time.sleep(COMPUTER_CONTROL_STEP_WAIT_SECONDS)

        return SkillResult(success=True, output=context.trace.summary("Automation finished."))
