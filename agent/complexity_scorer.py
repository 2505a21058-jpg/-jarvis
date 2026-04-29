"""
agent/complexity_scorer.py

Pure-Python input complexity scorer.
Replaces hardcoded keyword escalation triggers in fast_decide.py.
No external dependencies. Targets <1ms scoring per input.

Complexity dimensions measured:
1. Token count (word count proxy)
2. Clause density (conjunctions + punctuation)
3. Entity density (capitalized multi-word sequences)
4. Question complexity (nested vs simple)
5. Command multiplicity (multiple distinct action verbs)
6. Teach/learn intent (always escalate)
7. Explicit escalation markers (plan, step-by-step, etc.)
"""

from __future__ import annotations

import logging
import re


logger = logging.getLogger("jarvis.complexity_scorer")

_ACTION_VERBS = {
    "open", "search", "browse", "go", "find", "type", "click", "send",
    "download", "upload", "create", "delete", "move", "copy", "run",
    "start", "stop", "close", "save", "read", "write", "launch", "install",
}

_CLAUSE_CONNECTORS = {
    "and", "then", "after", "before", "while", "also", "next",
    "followed by", "once", "when", "finally", "additionally",
}

_HARD_ESCALATE_PATTERNS = [
    r"\bteach\b",
    r"\blearn how to\b",
    r"\bremember how to\b",
    r"\btrain you\b",
    r"\bnew skill\b",
    r"\bstep[\s-]by[\s-]step\b",
    r"\bmake a plan\b",
]
_HARD_ESCALATE_RE = [re.compile(pattern, re.IGNORECASE) for pattern in _HARD_ESCALATE_PATTERNS]


def _token_count(text: str) -> int:
    return len(text.split())


def _clause_density(text: str) -> float:
    """Returns ratio of clause connectors to total tokens."""
    tokens = text.lower().split()
    connector_count = sum(1 for token in tokens if token in _CLAUSE_CONNECTORS)
    connector_count += text.count(";") + max(0, text.count(",") - 1)
    return connector_count / max(len(tokens), 1)


def _action_verb_count(text: str) -> int:
    """Count distinct action verbs in input."""
    tokens = set(re.findall(r"\b\w+\b", text.lower()))
    return len(tokens & _ACTION_VERBS)


def _entity_density(text: str) -> float:
    """Estimate named entity density by counting capitalized word sequences."""
    capitalized_sequences = re.findall(r"(?:[A-Z][a-z]+\s?){2,}", text)
    return len(capitalized_sequences) / max(_token_count(text), 1)


def _question_complexity(text: str) -> int:
    """
    Score question complexity:
    0 = not a question
    1 = simple question (what is X)
    2 = comparative (X vs Y, difference between)
    3 = multi-part question (contains "and" + "?")
    """
    if "?" not in text:
        return 0
    text_lower = text.lower()
    if re.search(r"\b(vs|versus|difference between|compare)\b", text_lower):
        return 2
    if "and" in text_lower and text.count("?") > 1:
        return 3
    return 1


def compute_complexity_score(text: str) -> dict:
    """
    Compute a complexity profile for the input.
    Returns a dict with individual scores and a final 'escalate' recommendation.
    """
    text = str(text or "").strip()

    for pattern in _HARD_ESCALATE_RE:
        if pattern.search(text):
            return {
                "escalate": True,
                "reason": "hard_escalate_pattern",
                "token_count": _token_count(text),
                "action_verbs": _action_verb_count(text),
                "clause_density": 0.0,
                "entity_density": 0.0,
                "question_complexity": 0,
                "score": 1.0,
            }

    token_count = _token_count(text)
    action_verbs = _action_verb_count(text)
    clause_density = _clause_density(text)
    entity_density = _entity_density(text)
    question_complexity = _question_complexity(text)

    score = 0.0
    score += min(token_count / 40.0, 0.25)
    score += min(action_verbs / 3.0, 0.25)
    score += min(clause_density * 3.0, 0.20)
    score += min(entity_density * 4.0, 0.15)
    score += min(question_complexity / 3.0, 0.15)

    escalate = score >= 0.40 or token_count > 35
    reason = "score_threshold" if score >= 0.40 else (
        "length_threshold" if token_count > 35 else "within_fast_decide"
    )

    logger.debug(
        "Complexity: score=%.2f tokens=%s verbs=%s clauses=%.2f escalate=%s",
        score,
        token_count,
        action_verbs,
        clause_density,
        escalate,
    )

    return {
        "escalate": escalate,
        "reason": reason,
        "token_count": token_count,
        "action_verbs": action_verbs,
        "clause_density": round(clause_density, 3),
        "entity_density": round(entity_density, 3),
        "question_complexity": question_complexity,
        "score": round(score, 3),
    }


def should_use_fast_decide(user_input: str) -> bool:
    """
    Drop-in replacement for the old should_use_fast_decide() in fast_decide.py.
    Returns True if input is simple enough for Tier 2 handling.
    """
    result = compute_complexity_score(user_input)
    return not result["escalate"]
