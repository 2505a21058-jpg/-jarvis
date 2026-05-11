from __future__ import annotations

import json
import logging
import re
from typing import Any

from models.llm import JARVIS_CORE_MODEL, call_llm_fast_chat, run_llm
from skills.parser import extract_commands
from skills.registry import SkillRegistry


logger = logging.getLogger("jarvis.agent.decide")

ALLOWED_DECISION_TYPES = {"tool", "skill", "llm"}
FALLBACK_DECISION = {
    "type": "llm",
    "name": "chat",
    "confidence": 0.0,
    "reason": "Decision fallback",
    "requires_plan": False,
}
TEACH_TRIGGERS = ["teach you", "learn how to", "remember how to", "new skill:", "train you to"]
EXPLICIT_SKILL_PREFIXES = ("use learned skill ", "use skill ", "run ")
PLACEHOLDER_PATTERN = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")
NAMED_PARAM_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)=([\"'][^\"']*[\"']|\S+)")
HINT_NAME_MAP = {
    "open": {"open", "open_app"},
    "search": {"search", "search_web", "find", "watch"},
    "play": {"play", "play_music"},
    "type": {"type", "type_text"},
}
CHAT_KEYWORDS_EXCLUDE = [
    "open",
    "browse",
    "search",
    "type",
    "click",
    "run",
    "execute",
    "find file",
    "download",
]


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


def _select_primary_hint(decision_name: str, parser_hints: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not parser_hints:
        return None

    lowered_name = str(decision_name or "").strip().lower()
    for hint in parser_hints:
        intent = str(hint.get("intent", "")).strip().lower()
        aliases = HINT_NAME_MAP.get(intent, {intent})
        if lowered_name in aliases:
            return hint

    return parser_hints[0]


def _parameters_from_hint(decision_name: str, hint: dict[str, Any] | None) -> dict[str, Any]:
    if not hint:
        return {}

    target = str(hint.get("target", "")).strip()
    lowered_name = str(decision_name or "").strip().lower()
    if not target:
        return {}

    if lowered_name in {"open", "open_app"}:
        return {"target": target, "app_name": target}
    if lowered_name in {"search", "search_web", "find", "watch"}:
        return {"target": target, "query": target}
    if lowered_name in {"play", "play_music"}:
        return {"target": target, "source": target}
    if lowered_name in {"type", "type_text"}:
        return {"target": target, "text": target}
    return {"target": target}


def _enrich_decision(
    decision: dict[str, Any],
    observation: dict[str, Any],
    parser_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = dict(decision)
    state = observation.get("state", {})
    state_payload = dict(state) if isinstance(state, dict) else {}
    primary_hint = _select_primary_hint(enriched.get("name", ""), parser_hints)
    has_explicit_parameters = isinstance(enriched.get("parameters"), dict)
    parameters = dict(enriched.get("parameters", {})) if has_explicit_parameters else {}

    if not has_explicit_parameters:
        parameters = _parameters_from_hint(enriched.get("name", ""), primary_hint)

    enriched["parameters"] = parameters
    enriched["input"] = observation.get("input", "")
    enriched["mode"] = state_payload.get("mode", "fast")
    enriched["memory"] = observation.get("memory", {})
    enriched["recent_history"] = observation.get("recent_history", [])
    enriched["state"] = state_payload
    enriched["hints"] = parser_hints

    if len(parser_hints) > 1 and enriched.get("type") in {"tool", "skill"}:
        enriched["requires_plan"] = True

    return enriched


def _fallback_decision(user_input: Any, parser_hints: list[dict[str, Any]]) -> dict[str, Any]:
    if parser_hints:
        primary_hint = parser_hints[0]
        return {
            "type": "tool",
            "name": primary_hint["intent"],
            "confidence": min(float(primary_hint.get("confidence", 0.0)), 0.55),
            "reason": "Parser hint fallback",
            "requires_plan": len(parser_hints) > 1,
        }

    fallback = dict(FALLBACK_DECISION)
    fallback["reason"] = f"Fallback for input: {str(user_input or '').strip() or 'empty input'}"
    return fallback


def _combined_action_decision(
    combined: dict[str, Any],
    observation: dict[str, Any],
    parser_hints: list[dict[str, Any]],
) -> dict[str, Any]:
    action_type = str(combined.get("action_type", "")).strip().lower()
    action_name = str(combined.get("action_name", "")).strip().lower()
    parameters = combined.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}

    registered_skills = set(_registered_skill_names())
    known_skill_names = {"weather", "time", "date", "pnr", "train"} | registered_skills

    if action_type in ALLOWED_DECISION_TYPES:
        decision_type = action_type
        decision_name = action_name or ("chat" if decision_type == "llm" else "unknown")
    else:
        candidate_name = action_name or action_type or "unknown"
        decision_name = candidate_name
        decision_type = "skill" if candidate_name in known_skill_names else "tool"

    decision = {
        "type": decision_type,
        "name": decision_name,
        "confidence": 0.85,
        "reason": "LLM determined action required",
        "requires_plan": False,
        "parameters": parameters,
    }
    return _enrich_decision(decision, observation, parser_hints)


def _registered_skill_names() -> list[str]:
    try:
        names = [str(item.get("name", "")).strip() for item in SkillRegistry.instance().list_skills()]
    except Exception:
        return []

    return sorted({name for name in names if name})


def _skill_aliases(skill_name: str) -> set[str]:
    lowered = str(skill_name or "").strip().lower()
    if not lowered:
        return set()

    aliases = {lowered}
    aliases.add(lowered.replace("_", " "))
    aliases.add(lowered.replace("-", " "))
    return {alias.strip() for alias in aliases if alias.strip()}


def _skill_placeholders(skill: Any) -> list[str]:
    placeholders: set[str] = set()
    steps = getattr(skill, "steps", [])
    if not isinstance(steps, list):
        return []

    for step in steps:
        if not isinstance(step, dict):
            continue
        for value in (step.get("params") or {}).values():
            if not isinstance(value, str):
                continue
            placeholders.update(PLACEHOLDER_PATTERN.findall(value))

    return sorted(placeholders)


def _strip_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _extract_skill_invocation_params(remainder: str, skill: Any) -> dict[str, Any]:
    text = str(remainder or "").strip()
    if not text:
        return {}

    params: dict[str, Any] = {}
    consumed_spans = []

    for match in NAMED_PARAM_PATTERN.finditer(text):
        key = str(match.group(1) or "").strip()
        value = _strip_quotes(match.group(2) or "")
        if key:
            params[key] = value
            consumed_spans.append(match.span())

    leftover = text
    for start, end in reversed(consumed_spans):
        leftover = f"{leftover[:start]} {leftover[end:]}"
    leftover = re.sub(r"\s+", " ", leftover).strip()

    if leftover.lower().startswith("with "):
        leftover = leftover[5:].strip()

    placeholders = [name for name in _skill_placeholders(skill) if name not in params]
    if leftover and not params:
        parts = leftover.split(maxsplit=1)
        if len(parts) == 2 and parts[0].isidentifier():
            params[parts[0]] = parts[1].strip()
            leftover = ""

    if leftover and len(placeholders) == 1:
        params[placeholders[0]] = leftover
    elif leftover:
        params["raw_input"] = leftover

    return params


def _explicit_skill_decision(user_input: str) -> dict[str, Any] | None:
    normalized_input = re.sub(r"\s+", " ", str(user_input or "").strip())
    lowered_input = normalized_input.lower()
    if not lowered_input:
        return None

    registry = SkillRegistry.instance()
    candidates: list[tuple[str, str, Any]] = []
    for skill_name in _registered_skill_names():
        skill = registry.get(skill_name)
        if skill is None:
            continue
        for alias in _skill_aliases(skill_name):
            candidates.append((skill_name, alias, skill))

    candidates.sort(key=lambda item: len(item[1]), reverse=True)

    for prefix in EXPLICIT_SKILL_PREFIXES:
        if not lowered_input.startswith(prefix):
            continue

        remainder = normalized_input[len(prefix):].strip()
        lowered_remainder = remainder.lower()
        for skill_name, alias, skill in candidates:
            if lowered_remainder == alias:
                return {
                    "type": "skill",
                    "name": skill_name,
                    "confidence": 1.0,
                    "reason": "Explicit learned skill invocation",
                    "requires_plan": False,
                    "parameters": {},
                }

            if lowered_remainder.startswith(f"{alias} "):
                tail = remainder[len(alias):].strip()
                return {
                    "type": "skill",
                    "name": skill_name,
                    "confidence": 1.0,
                    "reason": "Explicit learned skill invocation",
                    "requires_plan": False,
                    "parameters": _extract_skill_invocation_params(tail, skill),
                }

    return None


def decide(observation: dict[str, Any]) -> dict[str, Any]:
    user_input = observation.get("input", "")
    from memory.personal_facts import format_facts_for_llm, search_facts, store_fact

    stored = store_fact(str(user_input or ""))
    if stored:
        logger.info("Personal fact detected and stored: %s", stored)

    relevant_facts = search_facts(str(user_input or ""))
    facts_context = format_facts_for_llm(relevant_facts) if relevant_facts else ""
    state_obj = observation.get("state_obj")
    recent_history = (
        state_obj.get_recent_conversation(n=6)
        if hasattr(state_obj, "get_recent_conversation")
        else list(observation.get("recent_history", []))[-6:]
    )
    parser_hints = _build_parser_hints(user_input)
    if any(trigger in user_input.lower() for trigger in TEACH_TRIGGERS):
        return {
            "type": "teach_skill",
            "name": "teach_skill",
            "confidence": 1.0,
            "reason": "User is teaching a new skill",
            "requires_plan": False,
            "parameters": {"raw_input": user_input},
        }
    explicit_skill = _explicit_skill_decision(user_input)
    if explicit_skill:
        return _enrich_decision(explicit_skill, observation, parser_hints)
    if parser_hints:
        fallback = _fallback_decision(user_input, parser_hints)
        return _enrich_decision(fallback, observation, parser_hints)

    is_likely_tool = any(keyword in user_input.lower() for keyword in CHAT_KEYWORDS_EXCLUDE)
    state_context = (
        state_obj.to_context_dict()
        if hasattr(state_obj, "to_context_dict")
        else dict(observation.get("state") or {})
    )
    if facts_context:
        state_context = dict(state_context or {})
        state_context["personal_facts"] = facts_context
    if not is_likely_tool and not parser_hints:
        try:
            combined = call_llm_fast_chat(
                user_input=user_input,
                state_context=state_context,
                recent_history=recent_history,
            )
        except Exception:
            combined = None

        if isinstance(combined, dict):
            if combined.get("is_chat"):
                decision = {
                    "type": "fast_chat",
                    "name": "respond",
                    "confidence": 0.95,
                    "reason": "Direct conversational response",
                    "requires_plan": False,
                    "parameters": {},
                    "direct_response": str(combined.get("response", "")).strip(),
                }
                return _enrich_decision(decision, observation, parser_hints)

            if combined.get("action_type") or combined.get("action_name"):
                return _combined_action_decision(combined, observation, parser_hints)

    prompt_payload = {
        "input": user_input,
        "memory": observation.get("memory"),
        "personal_facts": facts_context,
        "state": observation.get("state"),
        "recent_history": recent_history,
        "parser_hints": parser_hints,
    }

    system_prompt = (
        "You are the Jarvis decision engine.\n"
        "Decide the next execution path only.\n"
        "Parser hints are hints only and must not be treated as execution.\n"
        "Do not execute anything.\n"
        "Use PERSONAL FACTS when answering questions about the user.\n"
        "Supported tool names include open, search, play, type, open_app, search_web, play_music, type_text.\n"
        f"Supported skill names include weather, time, date, pnr, train, and registered skills: {', '.join(_registered_skill_names()) or 'none'}.\n"
        "Use llm for normal chat or when no tool/skill should run.\n"
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
            return _enrich_decision(decision, observation, parser_hints)
    except Exception:
        pass

    fallback = _fallback_decision(user_input, parser_hints)
    return _enrich_decision(fallback, observation, parser_hints)
