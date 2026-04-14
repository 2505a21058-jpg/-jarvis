from __future__ import annotations

from typing import Any, Callable
from urllib.parse import quote_plus

from models.llm import JARVIS_CORE_MODEL, run_llm


MAX_RETRIES = 2
FAILURE_PREFIXES = (
    "failed",
    "error",
    "i dont know how to open",
    "i don't know how to open",
    "nothing to type",
    "no active app",
    "could not",
    "please provide",
)


def _extract_parameters(decision: dict[str, Any]) -> dict[str, Any]:
    parameters = decision.get("parameters", {})
    if isinstance(parameters, dict):
        return dict(parameters)
    return {}


def _get_request_text(decision: dict[str, Any], parameters: dict[str, Any]) -> str:
    for key in ("input", "query", "prompt", "text", "observation_input"):
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("query", "target", "text", "app_name", "source", "value"):
        value = parameters.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    name = str(decision.get("name", "")).strip()
    return name


def _is_failure_output(output: Any) -> bool:
    if output is None:
        return True

    if isinstance(output, dict) and "success" in output:
        return not bool(output.get("success"))

    text = str(output).strip().lower()
    if not text:
        return True

    return text.startswith(FAILURE_PREFIXES)


def _make_result(
    success: bool,
    output: Any = None,
    error: str | None = None,
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "success": bool(success),
        "output": output,
        "error": error,
        "steps": steps or [],
    }


def _normalize_handler_output(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict) and {"success", "output", "error"} <= set(raw_output.keys()):
        return _make_result(
            bool(raw_output.get("success")),
            raw_output.get("output"),
            raw_output.get("error"),
            list(raw_output.get("steps") or []),
        )

    if _is_failure_output(raw_output):
        error_text = str(raw_output).strip() or "Execution failed."
        return _make_result(False, raw_output, error_text)

    return _make_result(True, raw_output, None)


def _tool_open(parameters: dict[str, Any]) -> Any:
    from skills.open_app import open_app

    target = str(
        parameters.get("target")
        or parameters.get("app_name")
        or parameters.get("name")
        or ""
    ).strip()
    if not target:
        return "No app target provided."
    return open_app(target)


def _tool_search(parameters: dict[str, Any]) -> Any:
    from skills.browser import browse

    target = str(parameters.get("query") or parameters.get("target") or "").strip()
    if not target:
        return "No search target provided."
    return browse(target)


def _tool_play(parameters: dict[str, Any]) -> Any:
    from skills.browser import browse

    source = str(parameters.get("source") or parameters.get("target") or "").strip()
    search_text = "!sp" if not source else f"!sp {source}"
    return browse(f"https://duckduckgo.com/?q={quote_plus(search_text)}")


def _tool_type(parameters: dict[str, Any]) -> Any:
    from skills.type_text import type_text

    text = str(parameters.get("text") or parameters.get("target") or "").strip()
    if not text:
        return "Nothing to type."
    return type_text(text)


def _skill_weather(parameters: dict[str, Any]) -> Any:
    from skills.weather import get_weather

    city = str(parameters.get("city") or parameters.get("target") or "Hyderabad").strip()
    return get_weather(city or "Hyderabad")


def _skill_time(parameters: dict[str, Any]) -> Any:
    from skills.datetime_skill import get_datetime

    return get_datetime()


def _skill_pnr(parameters: dict[str, Any]) -> Any:
    from skills.train import check_pnr

    pnr = str(parameters.get("pnr") or parameters.get("target") or "").strip()
    if not pnr:
        return "Please provide a valid PNR."
    return check_pnr(pnr)


def _skill_train(parameters: dict[str, Any]) -> Any:
    from skills.train import get_live_train

    train_number = str(parameters.get("train_number") or parameters.get("target") or "").strip()
    if not train_number:
        return "Please provide a valid train number."
    return get_live_train(train_number)


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "open": _tool_open,
    "open_app": _tool_open,
    "search": _tool_search,
    "search_web": _tool_search,
    "play": _tool_play,
    "play_music": _tool_play,
    "type": _tool_type,
    "type_text": _tool_type,
}

SKILL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "open": _tool_open,
    "search": _tool_search,
    "play": _tool_play,
    "type": _tool_type,
    "weather": _skill_weather,
    "time": _skill_time,
    "date": _skill_time,
    "pnr": _skill_pnr,
    "train": _skill_train,
}


def _run_llm_action(decision: dict[str, Any], *, error_context: str | None = None) -> dict[str, Any]:
    parameters = _extract_parameters(decision)
    request_text = _get_request_text(decision, parameters)

    system_prompt = (
        "You are Jarvis.\n"
        "Respond clearly and helpfully.\n"
        "If a tool failed, continue helpfully without pretending the tool succeeded."
    )
    user_prompt = request_text or "Help with the user's request."
    if error_context:
        user_prompt = f"Original request: {user_prompt}\nTool/skill failure: {error_context}"

    response = run_llm(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=str(decision.get("model") or JARVIS_CORE_MODEL),
        options=decision.get("options") if isinstance(decision.get("options"), dict) else None,
    )
    content = str(response.get("message", {}).get("content", "")).strip()
    if not content:
        return _make_result(False, None, "LLM returned empty output.")
    return _make_result(True, content, None)


def _execute_handler(
    label: str,
    handler: Callable[[dict[str, Any]], Any],
    parameters: dict[str, Any],
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    last_error = "Execution failed."

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw_output = handler(parameters)
            normalized = _normalize_handler_output(raw_output)
            steps.append(
                {
                    "attempt": attempt,
                    "action": label,
                    "success": normalized["success"],
                    "error": normalized["error"],
                }
            )
            if normalized["success"]:
                normalized["steps"] = steps
                return normalized
            last_error = normalized["error"] or last_error
        except Exception as exc:
            last_error = str(exc)
            steps.append(
                {
                    "attempt": attempt,
                    "action": label,
                    "success": False,
                    "error": last_error,
                }
            )

    return _make_result(False, None, last_error, steps)


def act(decision: dict[str, Any]) -> dict[str, Any]:
    decision = dict(decision or {})
    decision_type = str(decision.get("type", "")).strip().lower()
    decision_name = str(decision.get("name", "")).strip().lower()
    parameters = _extract_parameters(decision)
    steps: list[dict[str, Any]] = []

    if decision_type == "llm":
        llm_result = _run_llm_action(decision)
        llm_result["steps"] = [{"attempt": 1, "action": "llm", "success": llm_result["success"], "error": llm_result["error"]}]
        return llm_result

    if decision_type == "tool":
        handler = TOOL_HANDLERS.get(decision_name)
    elif decision_type == "skill":
        handler = SKILL_HANDLERS.get(decision_name)
    else:
        handler = None

    if handler is None:
        error_text = f"Unsupported decision target: {decision_type}:{decision_name}"
        fallback_result = _run_llm_action(decision, error_context=error_text)
        fallback_result["steps"] = [{"attempt": 1, "action": "llm_fallback", "success": fallback_result["success"], "error": error_text}]
        return fallback_result

    result = _execute_handler(f"{decision_type}:{decision_name}", handler, parameters, steps)
    if result["success"]:
        return result

    fallback_result = _run_llm_action(decision, error_context=result["error"])
    fallback_result["steps"] = steps + [
        {
            "attempt": 1,
            "action": "llm_fallback",
            "success": fallback_result["success"],
            "error": result["error"],
        }
    ]
    return fallback_result
