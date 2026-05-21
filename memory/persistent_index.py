from __future__ import annotations

import json
import logging
import math
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from config import EMBED_INPUT_MAX_CHARS, EMBED_MAX_ENTRIES, EMBED_MODEL, EMBED_TIMEOUT_SECONDS, OLLAMA_EMBEDDINGS_URL

logger = logging.getLogger("jarvis.memory.persistent")

_EMBED_MODEL = EMBED_MODEL
_EMBED_URL = OLLAMA_EMBEDDINGS_URL
_EMBED_TIMEOUT = EMBED_TIMEOUT_SECONDS
_MAX_ENTRIES = EMBED_MAX_ENTRIES
_TOTAL_FINGERPRINT = "jarvis_persistent_embedding_v1"


def _entry_text(entry: dict) -> str:
    parts = []
    for key in ("content", "value", "type", "key", "user", "jarvis", "input", "output", "query", "response", "skill_name"):
        value = entry.get(key)
        if value:
            parts.append(str(value))
    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(v) for v in metadata.values() if v)
    if not parts:
        parts.extend(str(v) for v in entry.values() if v)
    return " ".join(parts).strip()


def _get_embedding(text: str) -> Optional[list[float]]:
    try:
        import requests
        response = requests.post(
            _EMBED_URL,
            json={"model": _EMBED_MODEL, "prompt": str(text or "")[:EMBED_INPUT_MAX_CHARS]},
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
    try:
        a_arr = np.array(a, dtype=np.float64)
        b_arr = np.array(b, dtype=np.float64)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))
    except Exception as exc:
        logger.debug("Cosine similarity failed: %s", exc)
        return 0.0


class PersistentEmbeddingIndex:
    def __init__(self, max_entries: int = _MAX_ENTRIES, storage_dir: str = "memory/embeddings"):
        self._max_entries = max_entries
        self._storage_dir = Path(storage_dir)
        self._vectors_path = self._storage_dir / "vectors.npy"
        self._entries_path = self._storage_dir / "entries.json"
        self._lock = threading.Lock()
        self._available: Optional[bool] = None
        self._vectors: list[np.ndarray] = []
        self._entries: list[dict] = []
        self._load_persisted()

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        test = _get_embedding("test")
        self._available = test is not None
        if self._available:
            logger.info("Persistent embedding index ready (model=%s, persisted=%s)", _EMBED_MODEL, len(self._entries))
        else:
            logger.warning(
                "Embedding model '%s' not available. Run: ollama pull %s - falling back to TF-IDF only.",
                _EMBED_MODEL, _EMBED_MODEL,
            )
        return self._available

    def add(self, entry: dict) -> None:
        if not self._check_available():
            return

        def _embed_and_store() -> None:
            text = _entry_text(entry)
            if not text:
                return
            embedding = _get_embedding(text)
            if embedding:
                with self._lock:
                    self._vectors.append(np.array(embedding, dtype=np.float64))
                    self._entries.append(entry)
                    if len(self._entries) > self._max_entries:
                        excess = len(self._entries) - self._max_entries
                        self._vectors = self._vectors[excess:]
                        self._entries = self._entries[excess:]
                    self._persist()

        thread = threading.Thread(target=_embed_and_store, daemon=True)
        thread.start()

    def search(self, query: str, top_k: int = 10, threshold: float = 0.3) -> list[dict]:
        if not self._check_available():
            return []
        query_embedding = _get_embedding(query)
        if not query_embedding:
            return []
        q_vec = np.array(query_embedding, dtype=np.float64)

        with self._lock:
            if not self._vectors:
                return []
            vecs = np.array(self._vectors)
            entries = list(self._entries)

        norms = np.linalg.norm(vecs, axis=1)
        mask = norms > 0
        if not mask.any():
            return []
        scores = (vecs @ q_vec) / (norms * np.linalg.norm(q_vec) + 1e-10)

        indices = np.where(scores >= threshold)[0]
        ranked = sorted(zip(scores[indices], [entries[i] for i in indices]), key=lambda x: x[0], reverse=True)
        return [entry for _, entry in ranked[:top_k]]

    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def is_available(self) -> bool:
        return self._check_available()

    def _persist(self) -> None:
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            if self._vectors:
                stacked = np.stack(self._vectors)
                np.save(str(self._vectors_path), stacked)
            else:
                np.save(str(self._vectors_path), np.array([]))
            with open(self._entries_path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.debug("Embedding persist failed (non-critical): %s", exc)

    def _load_persisted(self) -> None:
        try:
            if self._vectors_path.exists() and self._entries_path.exists():
                arr = np.load(str(self._vectors_path))
                if arr.ndim == 2 and arr.shape[0] > 0:
                    self._vectors = [arr[i] for i in range(arr.shape[0])]
                with open(self._entries_path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
                if self._vectors and self._entries:
                    logger.info("Loaded %s persisted embeddings from %s", len(self._entries), self._storage_dir)
        except Exception as exc:
            logger.debug("Failed to load persisted embeddings: %s", exc)
            self._vectors = []
            self._entries = []
