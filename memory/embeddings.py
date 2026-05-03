"""
memory/embeddings.py

Local semantic embedding index for Jarvis memory.
Uses Ollama embedding API with nomic-embed-text model.
Runs alongside TF-IDF as a fallback - no replacement.

Setup: ollama pull nomic-embed-text
Environment: JARVIS_EMBED_MODEL (default: nomic-embed-text)

All storage operations enqueue embedding work in background threads.
Graceful degradation if model unavailable - TF-IDF handles everything.
"""

import logging
import math
import os
import threading
from typing import Optional


logger = logging.getLogger("jarvis.memory.embeddings")

_EMBED_MODEL = os.environ.get("JARVIS_EMBED_MODEL", "nomic-embed-text")
_EMBED_URL = "http://localhost:11434/api/embeddings"
_EMBED_TIMEOUT = 5.0
_MAX_ENTRIES = 1000
_TEXT_FIELDS = (
    "content",
    "value",
    "type",
    "key",
    "user",
    "jarvis",
    "input",
    "output",
    "query",
    "response",
    "skill_name",
)


def _get_embedding(text: str) -> Optional[list[float]]:
    """
    Call Ollama embeddings API for a single text string.
    Returns embedding vector or None on any failure.
    Truncates input to 512 chars to keep latency low.
    """
    try:
        import requests

        response = requests.post(
            _EMBED_URL,
            json={"model": _EMBED_MODEL, "prompt": str(text or "")[:512]},
            timeout=_EMBED_TIMEOUT,
        )
        if response.status_code == 200:
            embedding = response.json().get("embedding")
            return embedding if isinstance(embedding, list) else None
        logger.warning("Embedding API returned %s", response.status_code)
        return None
    except Exception as exc:
        logger.debug("Embedding call failed (non-critical): %s", exc)
        return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure Python cosine similarity. Returns 0.0 on any error."""
    try:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    except Exception:
        return 0.0


class EmbeddingIndex:
    """
    In-memory semantic index.
    Stores (embedding_vector, entry_dict) pairs.
    Built incrementally - no startup scan required.
    Falls back silently if Ollama embedding model unavailable.
    """

    def __init__(self, max_entries: int = _MAX_ENTRIES):
        self._entries: list[tuple[list[float], dict]] = []
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._available: Optional[bool] = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available

        test = _get_embedding("test")
        self._available = test is not None
        if self._available:
            logger.info("Semantic embedding index ready (model=%s)", _EMBED_MODEL)
        else:
            logger.warning(
                "Embedding model '%s' not available. Run: ollama pull %s - falling back to TF-IDF only.",
                _EMBED_MODEL,
                _EMBED_MODEL,
            )
        return self._available

    def add(self, entry: dict) -> None:
        """Add entry to semantic index in a background thread."""
        if not self._check_available():
            return

        def _embed_and_store() -> None:
            content = self._entry_text(entry)
            if not content:
                return

            embedding = _get_embedding(content)
            if embedding:
                with self._lock:
                    self._entries.append((embedding, entry))
                    if len(self._entries) > self._max_entries:
                        self._entries = self._entries[-self._max_entries :]

        thread = threading.Thread(target=_embed_and_store, daemon=True)
        thread.start()

    def search(self, query: str, top_k: int = 10, threshold: float = 0.3) -> list[dict]:
        """
        Search for semantically similar entries.
        Returns top_k entries above similarity threshold.
        Returns empty list if model unavailable.
        """
        if not self._check_available():
            return []

        query_embedding = _get_embedding(query)
        if not query_embedding:
            return []

        with self._lock:
            snapshot = list(self._entries)

        scored = [
            (entry, _cosine_similarity(query_embedding, embedding))
            for embedding, entry in snapshot
        ]
        scored = [(entry, score) for entry, score in scored if score >= threshold]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [entry for entry, _ in scored[:top_k]]

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def is_available(self) -> bool:
        return self._check_available()

    def _entry_text(self, entry: dict) -> str:
        if not isinstance(entry, dict):
            return str(entry or "")

        parts = []
        for key in _TEXT_FIELDS:
            value = entry.get(key)
            if value:
                parts.append(str(value))

        metadata = entry.get("metadata")
        if isinstance(metadata, dict):
            parts.extend(str(value) for value in metadata.values() if value)

        if not parts:
            parts.extend(str(value) for value in entry.values() if value)

        return " ".join(parts).strip()
