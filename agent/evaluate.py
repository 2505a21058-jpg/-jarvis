from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    passed: bool
    score: float
    issues: list[str] = field(default_factory=list)
    should_replan: bool = False
    failure_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        primary_issue = self.issues[0] if self.issues else None
        return {
            "passed": self.passed,
            "score": self.score,
            "issues": list(self.issues),
            "should_replan": self.should_replan,
            "failure_type": self.failure_type,
            "success": self.passed,
            "quality_score": self.score,
            "error": primary_issue,
            "retry_recommended": self.should_replan,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def _extract_output_text(result: dict[str, Any]) -> str:
    output = result.get("output")
    if output is None:
        return ""
    return str(output).strip()


def _normalize_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    return {
        "success": bool(response),
        "output": response,
        "error": None,
        "steps": [],
    }


def _classify_failure(error: str | None) -> str | None:
    text = str(error or "").strip().lower()
    if not text:
        return None
    if "timeout" in text:
        return "timeout"
    if "not found" in text:
        return "not_found"
    if "permission" in text or "denied" in text:
        return "permission"
    if "unavailable" in text or "connection" in text:
        return "unavailable"
    return "execution_error"


def _run_checks(response: Any, decision: dict[str, Any], state) -> EvaluationResult:
    _ = state
    result = _normalize_response(response)
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

    issues = [str(error).strip()] if error else []
    return EvaluationResult(
        passed=success,
        score=round(quality_score, 2),
        issues=issues,
        should_replan=retry_recommended,
        failure_type=_classify_failure(str(error).strip() if error else None),
    )


def evaluate(response: Any, decision: dict[str, Any], state) -> EvaluationResult:
    # Never allow replanning on retried decisions — prevents infinite loops
    if decision.get("_retry_attempt", False):
        result = _run_checks(response, decision, state)
        return EvaluationResult(
            passed=result.passed,
            score=result.score,
            issues=result.issues,
            should_replan=False,
            failure_type=result.failure_type,
        )
    return _run_checks(response, decision, state)
