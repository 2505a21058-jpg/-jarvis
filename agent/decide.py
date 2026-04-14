from __future__ import annotations

import json
from typing import Any

from models.llm import JARVIS_CORE_MODEL, run_llm
from skills.parser import extract_commands


ALLOWED_DECISION_TYPES = {"tool", "skill", "llm"}
FALLBACK_DECISION = {
    "type": "llm",
    "name": "chat",
    "confidence": 0.0,
    "reason": "Decision fallback",
    "requires_plan": False,
}


def _extract_json_object(text: str) -> dict[str, Any] | None:
    content = str(text or "").strip()
    if not content:
        return None

    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        data = json.loads(content[start:end + 1])
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _build_parser_hints(user_input: Any) -> list[dict[str, Any]]:
    hints = []
    for index, command in enumerate(extract_commands(str(user_input or ""))):
        intent = str(command.get("intent", "")).strip().lower()
        target = str(command.get("target", "")).strip()
        if not intent:
            continue

        hints.append(
            {
                "intent": intent,
                "target": target,
                "confidence": 0.8 if target else 0.5,
                "position": index,
            }
        )

    return hints


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _validate_decision(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None

    decision_type = str(data.get("type", "")).strip().lower()
    if decision_type not in ALLOWED_DECISION_TYPES:
        return None

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    confidence = max(0.0, min(1.0, confidence))
    name = str(data.get("name", "")).strip() or ("chat" if decision_type == "llm" else "unknown")
    reason = str(data.get("reason", "")).strip() or "No reason provided."

    return {
        "type": decision_type,
        "name": name,
        "confidence": confidence,
        "reason": reason,
        "requires_plan": _coerce_bool(data.get("requires_plan", False)),
    }


def _fallback_decision(user_input: Any, parser_hints: list[dict[str, Any]]) -> dict[str, Any]:
    if parser_hints:
        primary_hint = parser_hints[0]
        return {
            "type": "skill",
            "name": primary_hint["intent"],
            "confidence": min(float(primary_hint.get("confidence", 0.0)), 0.55),
            "reason": "Parser hint fallback",
            "requires_plan": len(parser_hints) > 1,
        }

    fallback = dict(FALLBACK_DECISION)
    fallback["reason"] = f"Fallback for input: {str(user_input or '').strip() or 'empty input'}"
    return fallback


def decide(observation: dict[str, Any]) -> dict[str, Any]:
    user_input = observation.get("input", "")
    parser_hints = _build_parser_hints(user_input)

    prompt_payload = {
        "input": user_input,
        "memory": observation.get("memory"),
        "state": observation.get("state"),
        "recent_history": observation.get("recent_history", []),
        "parser_hints": parser_hints,
    }

    system_prompt = (
        "You are the Jarvis decision engine.\n"
        "Decide the next execution path only.\n"
        "Parser hints are hints only and must not be treated as execution.\n"
        "Do not execute anything.\n"
        "Return ONLY strict JSON in this schema:\n"
        '{'
        '"type":"tool|skill|llm",'
        '"name":"...",'
        '"confidence":0.0,'
        '"reason":"...",'
        '"requires_plan":false'
        '}'
    )

    try:
        response = run_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=True)},
            ],
            model=JARVIS_CORE_MODEL,
            options={
                "temperature": 0,
                "num_predict": 180,
            },
        )
        content = response.get("message", {}).get("content", "")
        decision = _validate_decision(_extract_json_object(content))
        if decision:
            return decision
    except Exception:
        pass

    return _fallback_decision(user_input, parser_hints)
