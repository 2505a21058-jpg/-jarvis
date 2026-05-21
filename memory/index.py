"""
memory/index.py

BM25 search index over Jarvis memory entries.
Rebuilt incrementally as entries are added.
Separated from memory/core.py for clean architecture.

Install: pip install rank-bm25
"""

from __future__ import annotations

import logging
import re
import time


logger = logging.getLogger("jarvis.memory.index")

_INDEX_REBUILD_THRESHOLD = 50

try:
    from rank_bm25 import BM25Okapi

    _BM25_AVAILABLE = True
except ImportError:
    BM25Okapi = None
    _BM25_AVAILABLE = False
    logger.warning("[MEMORY INDEX] rank_bm25 not installed. pip install rank-bm25")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _entry_text(entry: dict) -> str:
    tags = entry.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    metadata = entry.get("metadata", {})
    metadata_text = " ".join(str(value) for value in metadata.values()) if isinstance(metadata, dict) else ""
    return " ".join(
        [
            str(entry.get("content", "")),
            str(entry.get("input", "")),
            str(entry.get("output", "")),
            str(entry.get("user", "")),
            str(entry.get("jarvis", "")),
            str(entry.get("query", "")),
            str(entry.get("response", "")),
            str(entry.get("type", "")),
            str(entry.get("memory_type", "")),
            " ".join(str(tag) for tag in tags),
            metadata_text,
        ]
    )


class MemoryIndex:
    """
    BM25 search index over a list of memory entry dicts.
    Rebuilt when entries change.
    """

    def __init__(self):
        self._entries: list[dict] = []
        self._corpus: list[list[str]] = []
        self._bm25 = None
        self._dirty_count = 0
        self._build_time: float = 0.0

    def build(self, entries: list[dict]) -> None:
        """Build index from scratch over all entries."""
        self._entries = list(entries or [])
        self._corpus = [_tokenize(_entry_text(entry)) for entry in self._entries]

        if _BM25_AVAILABLE and self._corpus:
            self._bm25 = BM25Okapi(self._corpus)
        else:
            self._bm25 = None

        self._dirty_count = 0
        self._build_time = time.time()
        logger.debug("[MEMORY INDEX] Built over %s entries", len(self._entries))

    def add(self, entry: dict) -> None:
        """Incrementally add one entry. Triggers full rebuild after threshold."""
        self._entries.append(entry)
        self._corpus.append(_tokenize(_entry_text(entry)))
        self._dirty_count += 1

        if self._dirty_count >= _INDEX_REBUILD_THRESHOLD:
            self.build(self._entries)

    def _fallback_scores(self, query_tokens: list[str]) -> list[float]:
        query_set = set(query_tokens)
        return [
            sum(1 for token in query_set if token in set(document)) / max(len(query_set), 1)
            for document in self._corpus
        ]

    def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.01,
    ) -> list[tuple[float, dict]]:
        """
        Search for entries relevant to query.
        Returns list of (score, entry) sorted by score descending.
        """
        if not self._entries:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        if self._bm25 and _BM25_AVAILABLE:
            scores = [float(score) for score in self._bm25.get_scores(query_tokens)]
        else:
            scores = self._fallback_scores(query_tokens)

        scored = [
            (float(scores[index]), self._entries[index])
            for index in range(len(self._entries))
            if float(scores[index]) >= min_score
        ]

        if not scored and self._bm25 and _BM25_AVAILABLE:
            fallback_scores = self._fallback_scores(query_tokens)
            scored = [
                (float(fallback_scores[index]), self._entries[index])
                for index in range(len(self._entries))
                if float(fallback_scores[index]) >= min_score
            ]

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:limit]

    @property
    def size(self) -> int:
        return len(self._entries)
