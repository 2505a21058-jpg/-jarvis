"""
agent/evaluate.py

Execution verification and response quality evaluation.
Called in the agent loop after act() completes.

Evaluation pipeline:
1. Rule-based checks (always, zero LLM cost)
2. LLM quality check (optional, only for chat/complex responses)
3. Return EvaluationResult with confidence score and retry recommendation

Confidence scoring:
  1.0 = definitely correct
  0.7 = probably correct
  0.5 = uncertain
  0.3 = likely wrong, consider retry
  0.0 = definitely failed
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("jarvis.evaluate")

_RETRY_CONFIDENCE_THRESHOLD = 0.4
_LLM_EVAL_MIN_LENGTH = 50
_LLM_EVAL_INTENTS = {"chat", "respond", "plan", "planner"}


@dataclass
class EvaluationResult:
    success: bool
    confidence: float
    issues: list[str] = field(default_factory=list)
    retry_recommended: bool = False
    correction: str = ""
    source: str = ""

    @property
    def passed(self) -> bool:
        return self.success

    @property
    def score(self) -> float:
        return self.confidence

    @property
    def should_replan(self) -> bool:
        return self.retry_recommended

    @property
    def failure_type(self) -> str | None:
        if self.success:
            return None
        issue_text = " ".join(self.issues).lower()
        if "timed out" in issue_text or "timeout" in issue_text:
            return "timeout"
        if "not found" in issue_text or "no such file" in issue_text:
            return "not_found"
        if "permission" in issue_text or "denied" in issue_text:
            return "permission"
        if "connection" in issue_text or "unavailable" in issue_text:
            return "unavailable"
        return "execution_error" if self.issues else None

    def to_dict(self) -> dict[str, Any]:
        primary_issue = self.issues[0] if self.issues else None
        return {
            "success": self.success,
            "confidence": self.confidence,
            "issues": list(self.issues),
            "retry_recommended": self.retry_recommended,
            "correction": self.correction,
            "source": self.source,
            # Legacy keys consumed by existing traces/state/tests.
            "passed": self.success,
            "score": self.confidence,
            "quality_score": self.confidence,
            "should_replan": self.retry_recommended,
            "failure_type": self.failure_type,
            "error": primary_issue,
        }

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


_HARD_FAILURE_PATTERNS = [
    r"traceback \(most recent call last\)",
    r"exception:",
    r"error:",
    r"attributeerror",
    r"typeerror",
    r"valueerror",
    r"filenotfounderror",
    r"permissionerror",
    r"failed to",
    r"could not",
    r"timed out",
    r"connection refused",
    r"no such file",
    r"skill not found",
]

_SOFT_FAILURE_PATTERNS = [
    r"i (couldn't|cannot|can't|was unable to)",
    r"i don't (know|have|understand)",
    r"(sorry|apologies),? i",
    r"not sure (how|what|if)",
    r"let me know if",
]

_EMPTY_INDICATORS = {"", "none", "null", "n/a", "undefined"}

_HALLUCINATION_INDICATORS = [
    r"as of my (last|knowledge) (update|cutoff)",
    r"i (don't|do not) have (access|real-time)",
    r"i cannot browse",
    r"i'm just an ai",
]


def _coerce_output(output: Any) -> str:
    if isinstance(output, dict):
        pieces = []
        if output.get("output") is not None:
            pieces.append(str(output.get("output")))
        if output.get("error"):
            pieces.append(str(output.get("error")))
        for step in output.get("steps") or []:
            if isinstance(step, dict) and step.get("error"):
                pieces.append(str(step.get("error")))
        return "\n".join(piece for piece in pieces if piece).strip()
    return "" if output is None else str(output).strip()


def _rule_evaluate(output: str, intent_name: str = "", exec_success: Optional[bool] = None) -> EvaluationResult:
    """
    Fast rule-based evaluation.
    Never calls LLM.
    """
    if not output or output.strip().lower() in _EMPTY_INDICATORS:
        return EvaluationResult(
            success=False,
            confidence=0.0,
            issues=["Empty or null output"],
            retry_recommended=True,
            source="rule",
        )

    lower = output.lower()
    issues = []
    confidence = 1.0

    # If the executor reports success, trust it — skip text-pattern checks
    if exec_success is not True:
        for pattern in _HARD_FAILURE_PATTERNS:
            if re.search(pattern, lower):
                issues.append(f"Hard failure pattern: '{pattern}'")
                confidence = min(confidence, 0.1)

        for pattern in _SOFT_FAILURE_PATTERNS:
            if re.search(pattern, lower):
                issues.append(f"Soft failure pattern: '{pattern}'")
                confidence = min(confidence, 0.5)

    if intent_name not in ("chat", "greeting", "acknowledgement"):
        for pattern in _HALLUCINATION_INDICATORS:
            if re.search(pattern, lower):
                issues.append("Possible hallucination - model refusing instead of executing")
                confidence = min(confidence, 0.4)

    if len(output.strip()) < 10 and intent_name not in ("greeting", "acknowledgement", "farewell"):
        issues.append("Suspiciously short output")
        confidence = min(confidence, 0.6)

    success = confidence >= _RETRY_CONFIDENCE_THRESHOLD
    return EvaluationResult(
        success=success,
        confidence=confidence,
        issues=issues,
        retry_recommended=confidence < _RETRY_CONFIDENCE_THRESHOLD,
        source="rule",
    )


def _llm_evaluate(output: str, original_input: str) -> Optional[EvaluationResult]:
    """
    Optional LLM-based quality check.
    Only called for long responses where quality matters.
    Returns None if LLM evaluation fails or is skipped.
    """
    try:
        from models.llm import call_llm_json

        result = call_llm_json(
            system=(
                "You are a response quality evaluator. "
                "Given a user request and Jarvis's response, evaluate quality. "
                "Return ONLY JSON: "
                '{"confidence": 0.0_to_1.0, "issues": ["list of problems"], '
                '"correction": "suggested fix or empty string"}'
                "\n\nBe strict. 1.0 = perfect. 0.0 = completely wrong or empty."
            ),
            user=f"User asked: {original_input}\n\nJarvis responded: {output}",
            temperature=0.0,
            max_tokens=200,
        )

        if result:
            confidence = float(result.get("confidence", 0.5))
            return EvaluationResult(
                success=confidence >= _RETRY_CONFIDENCE_THRESHOLD,
                confidence=confidence,
                issues=list(result.get("issues", []) or []),
                correction=str(result.get("correction", "") or ""),
                retry_recommended=confidence < _RETRY_CONFIDENCE_THRESHOLD,
                source="llm",
            )
    except Exception as e:
        logger.warning("LLM evaluation failed: %s", e)
    return None


def _legacy_call_args(output: Any, original_input: Any, intent_name: Any) -> tuple[str, str, str, bool]:
    """Support older evaluate(result, decision, state) callers while loop migrates."""
    if isinstance(original_input, dict):
        decision = original_input
        response_text = _coerce_output(output)
        original = ""
        resolved_intent = str(decision.get("intent") or decision.get("name") or "")
        retry_attempt = bool(decision.get("_retry_attempt", False))
        return response_text, original, resolved_intent, retry_attempt
    return _coerce_output(output), str(original_input or ""), str(intent_name or ""), False


def evaluate(
    output: Any,
    original_input: str = "",
    intent_name: str = "",
    use_llm: bool = False,
    exec_success: Optional[bool] = None,
) -> EvaluationResult:
    """
    Main evaluation entry point.
    Called from agent/loop.py after act() returns.
    """
    response_text, resolved_input, resolved_intent, retry_attempt = _legacy_call_args(
        output,
        original_input,
        intent_name,
    )

    rule_result = _rule_evaluate(response_text, resolved_intent, exec_success=exec_success)
    if retry_attempt and rule_result.retry_recommended:
        rule_result.retry_recommended = False

    if rule_result.confidence < 0.2:
        logger.warning(
            "[EVALUATE] Hard failure detected | confidence=%.2f | intent=%s | issues=%s",
            rule_result.confidence,
            resolved_intent,
            rule_result.issues,
        )
        return rule_result

    if (
        use_llm
        and resolved_intent.lower() in _LLM_EVAL_INTENTS
        and len(response_text) >= _LLM_EVAL_MIN_LENGTH
    ):
        llm_result = _llm_evaluate(response_text, resolved_input)
        if llm_result:
            combined_confidence = min(rule_result.confidence, llm_result.confidence)
            all_issues = rule_result.issues + llm_result.issues
            combined = EvaluationResult(
                success=combined_confidence >= _RETRY_CONFIDENCE_THRESHOLD,
                confidence=combined_confidence,
                issues=all_issues,
                correction=llm_result.correction,
                retry_recommended=combined_confidence < _RETRY_CONFIDENCE_THRESHOLD,
                source="combined",
            )
            logger.info(
                "[EVALUATE] source=combined confidence=%.2f intent=%s retry=%s issues=%s",
                combined.confidence,
                resolved_intent,
                combined.retry_recommended,
                combined.issues or "none",
            )
            return combined

    logger.debug(
        "[EVALUATE] source=rule confidence=%.2f intent=%s retry=%s issues=%s",
        rule_result.confidence,
        resolved_intent,
        rule_result.retry_recommended,
        rule_result.issues or "none",
    )
    return rule_result
