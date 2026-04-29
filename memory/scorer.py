"""
memory/scorer.py

Pure-Python TF-IDF relevance scorer for memory entries.
No external dependencies. Designed for <5ms scoring of 500-entry corpora.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter


logger = logging.getLogger("jarvis.memory.scorer")


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return [token for token in text.split() if len(token) > 2]


def _tf(tokens: list[str]) -> dict[str, float]:
    """Term frequency for a token list."""
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


class TFIDFScorer:
    """
    Incrementally updated TF-IDF index over memory entries.
    Supports add() as new entries arrive (no full reindex needed).
    """

    def __init__(self):
        self._doc_tokens: list[list[str]] = []
        self._doc_tf: list[dict[str, float]] = []
        self._df: dict[str, int] = {}
        self._n: int = 0

    def add(self, text: str) -> None:
        """Add a new document to the index."""
        tokens = _tokenize(text)
        tf = _tf(tokens)
        self._doc_tokens.append(tokens)
        self._doc_tf.append(tf)
        self._n += 1
        for term in set(tokens):
            self._df[term] = self._df.get(term, 0) + 1

    def score(self, query: str, doc_index: int) -> float:
        """TF-IDF cosine similarity between query and a document by index."""
        if doc_index >= self._n:
            return 0.0
        query_tokens = _tokenize(query)
        if not query_tokens:
            return 0.0

        doc_tf = self._doc_tf[doc_index]
        score = 0.0
        for term in query_tokens:
            if term in doc_tf:
                df = self._df.get(term, 1)
                idf = math.log((self._n + 1) / (df + 1)) + 1.0
                score += doc_tf[term] * idf
        return score

    def rank(self, query: str, indices: list[int], top_k: int = 10) -> list[tuple[int, float]]:
        """Return (index, score) pairs sorted descending by relevance."""
        scored = [(idx, self.score(query, idx)) for idx in indices]
        scored = [(idx, score) for idx, score in scored if score > 0.0]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:top_k]

    def rank_entries(self, query: str, entries: list[dict], top_k: int = 10) -> list[dict]:
        """
        Score a list of entry dicts directly (for use without index lookup).
        Each entry must have a 'content' key.
        Returns top_k entries sorted by relevance descending.
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return entries[:top_k]

        results = []
        for entry in entries:
            tokens = _tokenize(entry.get("content", ""))
            tf = _tf(tokens)
            score = 0.0
            for term in query_tokens:
                if term in tf:
                    df = self._df.get(term, 1)
                    idf = math.log((self._n + 1) / (df + 1)) + 1.0
                    score += tf[term] * idf
            if score > 0.0:
                results.append((entry, score))

        results.sort(key=lambda item: item[1], reverse=True)
        return [entry for entry, _ in results[:top_k]]
