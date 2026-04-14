from __future__ import annotations

from typing import Any


def _extract_output_text(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        return ""
    return str(output).strip()


def evaluate(result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    success = bool(result.get("success"))
    error = result.get("error")
    output_text = _extract_output_text(result)
    steps = list(result.get("steps") or [])
    decision_type = str(decision.get("type", "")).strip().lower()

    quality_score = 0.0
    retry_recommended = False

    if success:
        quality_score = 0.6

        if output_text:
            quality_score += 0.2
        if len(output_text) >= 20:
            quality_score += 0.1
        if steps:
            quality_score += 0.1

        quality_score = min(1.0, quality_score)
    else:
        quality_score = 0.1 if output_text else 0.0
        retry_recommended = decision_type in {"tool", "skill"} and bool(error)

    return {
        "success": success,
        "quality_score": round(quality_score, 2),
        "error": str(error).strip() if error else None,
        "retry_recommended": retry_recommended,
    }
