"""
memory/personal_facts.py

Dedicated store for personal facts about the user.
Completely separate from experience memory.
Stored in memory/personal_facts.jsonl - never pruned.

Examples of what gets stored:
  "user likes Fanta"
  "user's favorite language is Rust"
  "user's name is Shiva"
  "user prefers dark mode"

Retrieval is keyword-based across all stored facts.
Every fact is returned when the user asks about preferences/likes.
"""

import json
import logging
import os
import re
import time
from threading import Lock


logger = logging.getLogger("jarvis.memory.personal_facts")

FACTS_PATH = "memory/personal_facts.jsonl"

FACT_PATTERNS = [
    r"(?:remember(?: that)?|note that|keep in mind|don't forget)[,:]?\s+(?:i|my)\s+(.+)",
    r"(?:i|my)\s+(?:like|love|enjoy|prefer|favorite|favourite)\s+(.+)",
    r"(?:i|my)\s+(?:don't like|hate|dislike|can't stand)\s+(.+)",
    r"(?:i am|i'm)\s+(?:a\s+)?(.+)",
    r"my\s+(?:name|favorite|favourite|preferred|go-to)\s+(?:is|are)\s+(.+)",
    r"(?:i|my)\s+(?:use|work with|prefer to use)\s+(.+)",
    r"(?:save|store|remember)\s+(?:that\s+)?(?:i|my)\s+(.+)",
]

_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in FACT_PATTERNS]
_lock = Lock()


def _load_all_facts() -> list[dict]:
    """Load all personal facts from disk."""
    if not os.path.exists(FACTS_PATH):
        return []

    facts = []
    with open(FACTS_PATH, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                facts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return facts


def _save_fact(fact: dict) -> None:
    """Append a fact to disk."""
    os.makedirs(os.path.dirname(FACTS_PATH), exist_ok=True)
    with _lock:
        with open(FACTS_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(fact, ensure_ascii=False) + "\n")


def extract_fact(user_input: str) -> str | None:
    """
    Extract a personal fact from user input.
    Returns the fact string or None if input is not a fact statement.
    """
    text = str(user_input or "").strip()
    if not text:
        return None

    for pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            fact_content = match.group(0).strip()
            fact_content = re.sub(
                r"^(?:remember(?: that)?|note that|save that|store that)[,:]?\s*",
                "",
                fact_content,
                flags=re.IGNORECASE,
            ).strip()
            return fact_content
    return None


def store_fact(user_input: str) -> str | None:
    """
    Extract and store a personal fact.
    Returns the stored fact string or None if nothing was extracted.
    """
    fact = extract_fact(user_input)
    if not fact:
        return None

    existing = _load_all_facts()
    fact_lower = fact.lower()
    for entry in existing:
        if entry.get("fact", "").lower() == fact_lower:
            logger.debug("Fact already stored: %s", fact)
            return fact

    entry = {
        "fact": fact,
        "raw_input": user_input,
        "timestamp": time.time(),
    }
    _save_fact(entry)
    logger.info("Stored personal fact: %s", fact)
    return fact


def get_all_facts() -> list[str]:
    """Return all stored personal facts as strings."""
    return [entry.get("fact", "") for entry in _load_all_facts() if entry.get("fact")]


def search_facts(query: str) -> list[str]:
    """
    Search personal facts for query keywords.
    Returns matching fact strings.
    """
    all_facts = get_all_facts()
    if not all_facts:
        return []

    query_words = set(str(query or "").lower().split())
    stop_words = {
        "what",
        "do",
        "you",
        "know",
        "about",
        "me",
        "my",
        "remember",
        "recall",
        "tell",
        "i",
        "is",
        "are",
        "the",
        "a",
    }
    meaningful_words = query_words - stop_words

    if not meaningful_words:
        return all_facts

    scored = []
    for fact in all_facts:
        fact_words = set(fact.lower().split())
        overlap = len(meaningful_words & fact_words)
        scored.append((fact, overlap))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [fact for fact, _ in scored]


def format_facts_for_llm(facts: list[str]) -> str:
    """Format facts as a string for injection into LLM context."""
    if not facts:
        return ""

    lines = ["Personal facts about the user:"]
    for fact in facts[:10]:
        lines.append(f"  - {fact}")
    return "\n".join(lines)
