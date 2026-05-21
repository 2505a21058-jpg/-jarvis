from __future__ import annotations

import collections
import json
import logging
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from memory.embeddings import EmbeddingIndex
from memory.index import MemoryIndex as BM25MemoryIndex
from memory.persistent_index import PersistentEmbeddingIndex
from memory.scorer import TFIDFScorer


logger = logging.getLogger("jarvis.memory.core")


# ── TF-IDF Retrieval ──────────────────────────────────────────────────────────

_MEMORY_CONTEXT_BUDGET = int(os.getenv("JARVIS_MEMORY_BUDGET", "800"))  # tokens approx
_MEMORY_TYPE_WEIGHTS = {
    "experience": 1.4,
    "long_term": 1.2,
    "short_term": 1.0,
    "skill": 1.1,
}
_PRUNE_DAYS = int(os.getenv("JARVIS_MEMORY_PRUNE_DAYS", "30"))
_PRUNE_SCORE_THRESHOLD = float(os.getenv("JARVIS_MEMORY_PRUNE_SCORE", "0.1"))

_IMPORTANCE_WEIGHTS = {
    "experience": 1.5,
    "long_term": 1.3,
    "skill": 1.2,
    "short_term": 1.0,
    "recent": 1.0,
}
_TTL_DAYS = int(os.getenv("JARVIS_MEMORY_TTL_DAYS", "60"))
_TTL_MIN_IMPORTANCE = 0.2
_CONTEXT_BUDGET_TOKENS = int(os.getenv("JARVIS_MEMORY_BUDGET", "1000"))


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric."""
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _tfidf_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    corpus_df: dict[str, int],
    corpus_size: int,
) -> float:
    """
    Compute TF-IDF similarity between query and document.
    Returns float [0, 1].
    """
    if not doc_tokens or not query_tokens:
        return 0.0

    doc_tf = Counter(doc_tokens)
    doc_len = len(doc_tokens)
    score = 0.0

    for token in query_tokens:
        if token not in doc_tf:
            continue
        tf = doc_tf[token] / doc_len
        df = corpus_df.get(token, 1)
        idf = math.log((corpus_size + 1) / (df + 1)) + 1
        score += tf * idf

    return score / len(query_tokens) if query_tokens else 0.0


def _memory_entry_text(entry: dict) -> str:
    """Collect searchable text fields without changing the persisted memory shape."""
    if not isinstance(entry, dict):
        return str(entry or "")

    text_fields = (
        "content",
        "value",
        "input",
        "output",
        "query",
        "response",
        "user",
        "jarvis",
        "skill_name",
        "key",
        "type",
    )
    parts = [str(entry.get(key)) for key in text_fields if entry.get(key)]

    tags = entry.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags if tag)

    metadata = entry.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value) for value in metadata.values() if value)

    if not parts:
        parts.extend(str(value) for value in entry.values() if value)

    return " ".join(parts)


def _build_corpus_df(entries: list[dict]) -> tuple[dict[str, int], int]:
    """Build document frequency table from all memory entries."""
    df: dict[str, int] = {}
    for entry in entries:
        tokens = set(_tokenize(_memory_entry_text(entry)))
        for token in tokens:
            df[token] = df.get(token, 0) + 1
    return df, len(entries)


def _estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token."""
    return max(1, len(str(text or "")) // 4)


def _parse_memory_datetime(value: Any) -> datetime | None:
    """Normalize persisted timestamp styles so recency/pruning work across old files."""
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _recency_boost(entry: dict) -> float:
    """Boost recent memories. Returns multiplier [0.5, 1.5]."""
    created = _parse_memory_datetime(entry.get("timestamp") or entry.get("created_at"))
    if created is None:
        return 1.0

    try:
        now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
        age_days = (now - created).days
    except Exception:
        return 1.0

    if age_days <= 1:
        return 1.5
    if age_days <= 7:
        return 1.2
    if age_days <= 30:
        return 1.0
    return 0.7


def _memory_type_weight(entry: dict) -> float:
    """Apply source weighting while preserving learned-skill records' original type."""
    raw_type = str(
        entry.get("_memory_type")
        or entry.get("memory_type")
        or entry.get("type")
        or "short_term"
    ).strip().lower()
    normalized = "short_term" if raw_type in {"recent", "short"} else raw_type
    if "skill" in normalized:
        normalized = "skill"
    return _MEMORY_TYPE_WEIGHTS.get(normalized, 1.0)


def compute_importance(entry: dict) -> float:
    """
    Compute normalized importance score for a memory entry.

    Factors:
    - access_count: how often this memory has been retrieved
    - recency: how recently it was created/accessed
    - memory_type: experience > long_term > skill > short_term
    - eval_confidence: successful interactions score higher
    """
    ts = entry.get("timestamp") or entry.get("created_at", 0)
    try:
        if isinstance(ts, str):
            created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(created.tzinfo) if created.tzinfo else datetime.now()
        elif ts:
            created = datetime.fromtimestamp(float(ts))
            now = datetime.now()
        else:
            created = datetime.now()
            now = datetime.now()
        age_days = max(0, (now - created).days)
        recency = math.exp(-age_days / 30)
    except Exception:
        recency = 0.5

    access = min(int(entry.get("access_count", 0) or 0), 20)
    access_score = access / 40.0

    mem_type = str(
        entry.get("_memory_type")
        or entry.get("memory_type")
        or entry.get("type")
        or "short_term"
    ).strip().lower()
    if "skill" in mem_type:
        mem_type = "skill"
    type_weight = _IMPORTANCE_WEIGHTS.get(mem_type, 1.0) / 1.5

    eval_conf = entry.get("metadata", {}).get("eval_confidence", None) if isinstance(entry.get("metadata"), dict) else None
    conf_factor = float(eval_conf) if eval_conf is not None else 0.75

    raw = (recency * 0.4) + (access_score * 0.3) + (type_weight * 0.15) + (conf_factor * 0.1)
    return min(1.0, max(0.0, raw))


def auto_tag(content: str) -> list[str]:
    """Auto-extract simple tags from memory content without an NLP dependency."""
    tags = []
    content_text = str(content or "")
    content_lower = content_text.lower()

    if re.search(r"https?://", content_text):
        tags.append("web")

    apps = [
        "chrome", "firefox", "vscode", "notepad", "youtube", "gmail",
        "spotify", "discord", "telegram", "slack", "excel", "word",
    ]
    for app in apps:
        if app in content_lower:
            tags.append(f"app:{app}")

    if any(word in content_lower for word in ["open", "launch", "start"]):
        tags.append("action:open")
    if any(word in content_lower for word in ["type", "write", "input"]):
        tags.append("action:type")
    if any(word in content_lower for word in ["search", "find", "look"]):
        tags.append("action:search")
    if re.search(r"\b\d+\s*(minute|hour|day|week|month)", content_lower):
        tags.append("time_sensitive")

    return sorted(set(tags))


def retrieve_bm25(
    query: str,
    index,
    entries: list[dict],
    limit: int = 8,
    mode: str = "full",
    budget_tokens: int | None = None,
) -> list[dict]:
    """
    BM25-based retrieval with importance re-ranking and context budgeting.
    """
    if not entries:
        return []

    normalized_limit = int(max(limit or 0, 0))
    if normalized_limit <= 0:
        return []

    if str(mode or "").lower() == "fast":
        return sorted(
            entries,
            key=lambda entry: entry.get("timestamp", entry.get("created_at", 0)),
            reverse=True,
        )[: min(normalized_limit, 3)]

    scored = index.search(query, limit=normalized_limit * 2)
    if not scored:
        return []

    reranked = []
    for bm25_score, entry in scored:
        importance = compute_importance(entry)
        norm_bm25 = min(1.0, max(0.0, bm25_score / 5.0))
        combined = (norm_bm25 * 0.6) + (importance * 0.4)
        reranked.append((combined, entry))

    reranked.sort(key=lambda item: item[0], reverse=True)

    budget = int(budget_tokens or _CONTEXT_BUDGET_TOKENS)
    result = []
    tokens_used = 0
    for _score, entry in reranked:
        entry_tokens = _estimate_tokens(_memory_entry_text(entry))
        if tokens_used + entry_tokens > budget:
            continue
        result.append(entry)
        tokens_used += entry_tokens
        if len(result) >= normalized_limit:
            break
    return result


def prune_by_ttl(entries: list[dict]) -> tuple[list[dict], int]:
    """Remove low-importance entries older than TTL."""
    cutoff = datetime.now() - timedelta(days=_TTL_DAYS)
    kept = []
    removed = 0

    for entry in entries:
        ts = entry.get("timestamp") or entry.get("created_at", 0)
        try:
            if isinstance(ts, str):
                created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if created.tzinfo is not None:
                    created = created.replace(tzinfo=None)
            elif ts:
                created = datetime.fromtimestamp(float(ts))
            else:
                kept.append(entry)
                continue

            if created < cutoff and compute_importance(entry) < _TTL_MIN_IMPORTANCE:
                removed += 1
                continue
        except Exception:
            pass
        kept.append(entry)

    if removed:
        logger.info("[MEMORY] Pruned %s expired low-importance entries", removed)
    return kept, removed


def retrieve_relevant(
    query: str,
    entries: list[dict],
    limit: int = 8,
    budget_tokens: int | None = None,
    mode: str = "full",
) -> list[dict]:
    """
    Retrieve memories relevant to query using TF-IDF + recency + type weighting.

    Args:
        query: The user input to find relevant memories for
        entries: All memory entries to search
        limit: Max entries to return before budget pruning
        budget_tokens: Max total tokens of memories to return
        mode: "fast" (most recent top-3) or "full" (scored + budgeted)

    Returns:
        List of memory entries, sorted by relevance score descending.
    """
    if not entries:
        return []

    normalized_limit = int(max(limit or 0, 0))
    if normalized_limit <= 0:
        return []

    budget = int(budget_tokens or _MEMORY_CONTEXT_BUDGET)

    def within_budget(candidate_entries: list[dict]) -> list[dict]:
        result = []
        tokens_used = 0
        for entry in candidate_entries:
            entry_tokens = _estimate_tokens(_memory_entry_text(entry))
            if tokens_used + entry_tokens > budget:
                continue
            result.append(entry)
            tokens_used += entry_tokens
            if len(result) >= normalized_limit:
                break
        return result

    if str(mode or "").lower() == "fast":
        sorted_recent = sorted(
            entries,
            key=lambda entry: entry.get("timestamp", entry.get("created_at", 0)),
            reverse=True,
        )
        fast_limit = min(normalized_limit, 3)
        if _tokenize(query):
            # Fast mode still scores recent entries so chat context does not drift off-topic.
            return retrieve_relevant(query, sorted_recent, limit=fast_limit, budget_tokens=budget, mode="full")
        return within_budget(sorted_recent[:fast_limit])

    query_tokens = _tokenize(query)
    if not query_tokens:
        return within_budget(list(reversed(entries))[:normalized_limit])

    bm25_index = BM25MemoryIndex()
    bm25_index.build(entries)
    bm25_results = retrieve_bm25(
        query,
        bm25_index,
        entries,
        limit=normalized_limit,
        mode="full",
        budget_tokens=budget,
    )
    if bm25_results:
        return bm25_results

    corpus_df, corpus_size = _build_corpus_df(entries)

    scored: list[tuple[float, dict]] = []
    for entry in entries:
        doc_tokens = _tokenize(_memory_entry_text(entry))
        base_score = _tfidf_score(query_tokens, doc_tokens, corpus_df, corpus_size)
        final_score = base_score * _memory_type_weight(entry) * _recency_boost(entry)
        scored.append((final_score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)

    # Budgeted TF-IDF retrieval replaces loose substring matches to avoid bloated LLM context.
    ranked = [entry for score, entry in scored if score >= 0.01]
    return within_budget(ranked)


def prune_stale_memories(entries: list[dict]) -> tuple[list[dict], int]:
    """
    Remove memories older than _PRUNE_DAYS with low relevance indicators.
    Returns (pruned_list, removed_count).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_PRUNE_DAYS)
    kept = []
    removed = 0

    for entry in entries:
        created = _parse_memory_datetime(entry.get("timestamp") or entry.get("created_at"))
        if created is None:
            kept.append(entry)
            continue

        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)

        score = float(entry.get("score", entry.get("relevance_score", 0.0)) or 0.0)
        access_count = int(entry.get("access_count", 0) or 0)
        if created < cutoff and score < _PRUNE_SCORE_THRESHOLD and access_count <= 0:
            removed += 1
            continue

        kept.append(entry)

    return kept, removed


def get_stats(memory: "Memory" | None = None) -> dict[str, Any]:
    """Return read-only memory diagnostics without touching persistence."""
    if memory is None:
        return {
            "recent": 0,
            "long_term": 0,
            "experience": 0,
            "profile": 0,
            "total": 0,
            "semantic_available": False,
        }

    recent = len(getattr(memory, "_recent_index").entries())
    long_term = len(getattr(memory, "_long_term_index").entries())
    experience = len(getattr(memory, "_experience_index").entries())
    try:
        profile = len(memory._profile_candidates())
    except Exception:
        profile = 0

    return {
        "recent": recent,
        "long_term": long_term,
        "experience": experience,
        "profile": profile,
        "total": recent + long_term + experience + profile,
        "semantic_available": bool(memory.is_semantic_available()),
    }


class MemoryIndex:
    """
    In-memory index over JSONL entries.
    Built once at startup, updated incrementally on store().
    Provides O(1) tag lookup and bounded recent() without re-reading disk.
    """

    TEXT_FIELDS = (
        "content", "value", "type", "key", "user", "jarvis", "input", "output",
        "query", "response", "skill_name",
    )

    def __init__(self, max_recent: int = 200):
        self._entries: list[dict] = []
        self._tag_index: dict[str, list[int]] = collections.defaultdict(list)
        self._lock = Lock()
        self._max_recent = max_recent
        self._scorer = TFIDFScorer()

    def load_from_jsonl(self, path: str | Path) -> None:
        """Read existing JSONL once at startup and populate index."""
        source = Path(path)
        if not source.exists():
            return

        with source.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                for entry in self._parse_json_objects(line):
                    self._add_entry(entry)

    def add(self, entry: dict) -> None:
        with self._lock:
            self._add_entry(entry)

    def recent(self, n: int) -> list[dict]:
        with self._lock:
            return list(self._entries[-int(max(n, 0)) :]) if n > 0 else []

    def search_by_tags(self, tags: list[str]) -> list[dict]:
        with self._lock:
            seen = set()
            results = []
            for tag in tags:
                for idx in self._tag_index.get(str(tag), []):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    results.append(self._entries[idx])
            return results

    def entries(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[dict]:
        """
        Relevance-ranked keyword search using TF-IDF scoring.
        Falls back to recency if no scored results.
        """
        normalized_limit = int(max(limit or 0, 0))
        if normalized_limit <= 0:
            return []

        query_text = str(keyword or "").strip()
        if not query_text:
            return self.recent(normalized_limit)

        with self._lock:
            # Use the shared budgeted scorer so index lookup and Memory.retrieve rank identically.
            ranked = retrieve_relevant(query_text, list(self._entries), limit=normalized_limit)
            if ranked:
                return ranked

        return self.recent(normalized_limit)

    def _add_entry(self, entry: dict) -> None:
        if not isinstance(entry, dict):
            return

        idx = len(self._entries)
        self._entries.append(entry)
        self._scorer.add(self._entry_text(entry))
        for tag in entry.get("tags", []) or []:
            self._tag_index[str(tag)].append(idx)

    def _entry_text(self, entry: dict) -> str:
        parts = []
        for key in self.TEXT_FIELDS:
            value = entry.get(key)
            if value:
                parts.append(str(value).lower())

        metadata = entry.get("metadata")
        if isinstance(metadata, dict):
            parts.extend(str(value).lower() for value in metadata.values() if value)

        if not parts:
            parts.extend(str(value).lower() for value in entry.values() if value)

        return " ".join(parts)

    def _parse_json_objects(self, text: str) -> list[dict]:
        decoder = json.JSONDecoder()
        records = []
        index = 0

        while index < len(text):
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                break

            try:
                value, next_index = decoder.raw_decode(text, index)
            except Exception as exc:
                # Malformed concatenated JSON stops parsing with debug context instead of failing load.
                logger.debug("Stopped parsing concatenated JSON objects at offset %s: %s", index, exc)
                break

            if isinstance(value, dict):
                records.append(value)
            index = next_index

        return records


class Memory:
    STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
        "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "so",
        "that", "the", "this", "to", "was", "we", "what", "when", "where", "who",
        "why", "with", "you", "your"
    }
    PROFILE_KEYS = {"name", "facts", "core_memory"}
    RECENT_KEYS = {"user", "jarvis", "input", "output", "query", "response"}
    MODE_LIMITS = {
        "fast": {"matches": 2, "recent": 3},
        "smart": {"matches": 5, "recent": 5},
        "nerd": {"matches": 8, "recent": 8},
        "deep": {"matches": 10, "recent": 8},
    }

    def __init__(self, base_dir: str | Path = "memory"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.profile_path = self.base_dir / "user_profile.json"
        self._recent_path = self.base_dir / "recent.jsonl"
        self._long_term_path = self.base_dir / "long_term.jsonl"
        self._experience_path = self.base_dir / "experiences.jsonl"

        # Compatibility aliases for existing callers and existing persisted files.
        self.recent_path = self._recent_path
        self.memory_path = self._long_term_path
        self._legacy_recent_paths = [self.base_dir / "recent_memories.jsonl"]
        self._legacy_long_term_paths = [self.base_dir / "memory.jsonl"]
        self._legacy_experience_paths: list[Path] = []

        self._recent_index = MemoryIndex(max_recent=200)
        self._long_term_index = MemoryIndex(max_recent=2000)
        self._experience_index = MemoryIndex(max_recent=500)
        self._bm25_index = BM25MemoryIndex()
        self._embed_index = EmbeddingIndex(max_entries=1000)
        self._persistent_index = PersistentEmbeddingIndex(max_entries=1000)

        self._profile_lock = Lock()
        self._profile_cache: dict[str, Any] = {}
        self._profile_view: dict[str, Any] = {}
        self._profile_candidates_cache: list[dict[str, Any]] = []
        self._load_profile_cache()

        self._load_index(self._recent_index, [self._recent_path, *self._legacy_recent_paths])
        self._load_index(self._long_term_index, [self._long_term_path, *self._legacy_long_term_paths])
        self._load_index(self._experience_index, [self._experience_path, *self._legacy_experience_paths])
        self._rebuild_index()

    def store(
        self,
        data: Any = None,
        *,
        content: Any = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        memory_type: str = "recent",
    ):
        if content is not None or tags is not None or metadata is not None or memory_type != "recent":
            payload = content if content is not None else data
            return self._store_structured(payload, tags=tags, metadata=metadata, memory_type=memory_type)

        if isinstance(data, list):
            return [self.store(item) for item in data]

        if self._looks_like_profile_payload(data):
            return self._store_profile(data)

        record = self._normalize_record(data)
        if self._looks_like_recent_record(record):
            record = self._prepare_memory_entry(record, "short_term")
            self._append_indexed_jsonl(self._recent_path, self._recent_index, record)
        else:
            record = self._prepare_memory_entry(record, str(record.get("memory_type") or record.get("type") or "long_term"))
            self._append_indexed_jsonl(self._long_term_path, self._long_term_index, record)
        return record

    def add(
        self,
        content: str,
        memory_type: str = "short_term",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Compatibility API for adding one structured memory entry."""
        merged_metadata = dict(metadata or {})
        merged_metadata.update(kwargs.pop("metadata_extra", {}) if isinstance(kwargs.get("metadata_extra"), dict) else {})
        if kwargs:
            merged_metadata.update(kwargs)
        normalized_type = "recent" if str(memory_type).lower() in {"short_term", "short", "recent"} else memory_type
        return self.store(
            content=content,
            tags=tags or [],
            metadata=merged_metadata,
            memory_type=normalized_type,
        )

    def retrieve(self, query, mode="full", limit: int | None = None):
        mode_name = str(mode or "full").strip().lower()
        default_limit = int(limit or 8)
        query_text = str(query or "")

        if mode_name == "recent":
            return retrieve_relevant(
                query_text,
                self._with_memory_type(self._recent_index.entries(), "short_term"),
                limit=default_limit,
                mode="fast",
            )

        if mode_name == "semantic":
            results = self._persistent_index.search(query_text, top_k=default_limit)
            if not results:
                results = self._embed_index.search(query_text, top_k=default_limit)
            if not results:
                return retrieve_relevant(query_text, self._get_all_entries(), limit=default_limit)
            return results

        if mode_name == "tags":
            tags = query if isinstance(query, list) else str(query or "").split()
            candidates = (
                self._with_memory_type(self._recent_index.search_by_tags(tags), "short_term")
                + self._with_memory_type(self._long_term_index.search_by_tags(tags), "long_term")
                + self._with_memory_type(self._experience_index.search_by_tags(tags), "experience")
            )
            deduped = self._dedupe_records(candidates)
            ranked = retrieve_relevant(" ".join(str(tag) for tag in tags), deduped, limit=default_limit)
            if ranked:
                return ranked
            return deduped[:default_limit]

        if mode_name == "deep":
            ranked = retrieve_bm25(query_text, self._bm25_index, self._get_all_entries(), limit=default_limit)
            if not ranked:
                semantic = self._persistent_index.search(query_text, top_k=default_limit)
                if not semantic:
                    semantic = self._embed_index.search(query_text, top_k=default_limit)
                if semantic:
                    logger.debug("BM25 miss (deep) - semantic fallback returned %s results", len(semantic))
                    return semantic
            return ranked

        if mode_name == "fast" and query_text.strip():
            results = retrieve_relevant(
                query_text,
                self._with_memory_type(self._recent_index.entries(), "short_term"),
                limit=default_limit,
                mode="fast",
            )
            if not results:
                semantic = self._embed_index.search(query_text, top_k=default_limit)
                if semantic:
                    logger.debug("TF-IDF miss - semantic fallback returned %s results", len(semantic))
                    return semantic
            return results

        # All general modes now return a ranked, budgeted list instead of unbounded keyword buckets.
        results = retrieve_bm25(query_text, self._bm25_index, self._get_all_entries(), limit=default_limit)
        if not results and query_text.strip():
            semantic = self._embed_index.search(query_text, top_k=default_limit)
            if semantic:
                logger.debug("BM25 miss (%s) - semantic fallback returned %s results", mode_name, len(semantic))
                return semantic
        return results

    def recent(self, limit=5, n: int | None = None):
        count = int(n if n is not None else limit)
        if count <= 0:
            return []
        return self._recent_index.recent(count)

    def store_experience(self, content: str, tags: list[str] | None = None) -> None:
        """Stores to experience memory. Called by agent/learn.py."""
        self.store(content=content, tags=tags or [], memory_type="experience")

    def prune_experiences(self, max_entries: int = 1000) -> None:
        all_entries, removed = prune_stale_memories(self._experience_index.entries())
        entries = all_entries[-int(max_entries or 0) :] if max_entries else all_entries
        self._experience_path.parent.mkdir(parents=True, exist_ok=True)
        with self._experience_path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self._experience_index = MemoryIndex(max_recent=500)
        self._experience_index.load_from_jsonl(self._experience_path)
        self._rebuild_index()
        if removed:
            logger.info("Pruned %s stale low-value experience memories", removed)

    def prune(self) -> int:
        """Prune expired low-importance memories and rebuild indexes."""
        removed = 0
        removed += self._prune_index(self._recent_path, "_recent_index", "short_term", 200)
        removed += self._prune_index(self._long_term_path, "_long_term_index", "long_term", 2000)
        removed += self._prune_index(self._experience_path, "_experience_index", "experience", 500)
        if removed:
            self._rebuild_index()
        return removed

    def promote_to_long_term(self, entry: dict) -> None:
        import os

        fingerprint = str(entry.get("content", ""))[:80].lower().strip()
        with self._long_term_index._lock:
            for existing in self._long_term_index._entries[-20:]:
                if str(existing.get("content", ""))[:80].lower().strip() == fingerprint:
                    logger.debug("promote_to_long_term: duplicate detected, skipping")
                    return

        promoted_entry = {
            **entry,
            "promoted_at": time.time(),
            "tags": list(set(list(entry.get("tags", []) or []) + ["promoted"])),
        }

        os.makedirs(os.path.dirname(self._long_term_path), exist_ok=True)
        with open(self._long_term_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(promoted_entry, ensure_ascii=False) + "\n")

        self._long_term_index.add(promoted_entry)
        self._bm25_index.add(self._prepare_memory_entry(dict(promoted_entry), "long_term"))
        self._add_to_embedding_index(promoted_entry)
        logger.info("Promoted entry to long_term memory")

    def search_semantic(self, query: str, top_k: int = 10) -> list[dict]:
        """
        Semantic similarity search using local embeddings.
        Returns relevant entries even when keywords do not match.
        Returns empty list if embedding model is not available.
        """
        return self._embed_index.search(query, top_k=top_k, threshold=0.3)

    def is_semantic_available(self) -> bool:
        """Returns True if embedding model is accessible via Ollama."""
        return self._persistent_index.is_available() or self._embed_index.is_available()

    def run_promotion_sweep(self, min_importance: float = 0.8) -> int:
        promoted = 0
        long_term_fingerprints = {
            str(entry.get("content", ""))[:80].lower().strip()
            for entry in self._long_term_index.entries()
        }

        for entry in self._experience_index.entries():
            try:
                data = json.loads(str(entry.get("content", "{}")))
                importance = float(data.get("importance", 0.0))
            except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
                importance = 0.0

            if importance >= min_importance:
                fingerprint = str(entry.get("content", ""))[:80].lower().strip()
                if fingerprint not in long_term_fingerprints:
                    entry_with_meta = {
                        **entry,
                        "metadata": {**dict(entry.get("metadata", {}) or {}), "importance": importance},
                    }
                    self.promote_to_long_term(entry_with_meta)
                    long_term_fingerprints.add(fingerprint)
                    promoted += 1

        logger.info("Promotion sweep complete: %s entries promoted to long_term", promoted)
        return promoted

    def _store_structured(
        self,
        content: Any,
        *,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        memory_type: str = "recent",
    ) -> dict[str, Any]:
        entry = {
            "content": self._stringify_content(content),
            "tags": list(tags or []),
            "metadata": dict(metadata or {}),
            "timestamp": time.time(),
        }

        if entry["metadata"].get("type") and "type" not in entry:
            entry["type"] = entry["metadata"]["type"]
        if entry["metadata"].get("skill_name") and "skill_name" not in entry:
            entry["skill_name"] = entry["metadata"]["skill_name"]

        path_map = {
            "recent": (self._recent_path, self._recent_index),
            "short_term": (self._recent_path, self._recent_index),
            "long_term": (self._long_term_path, self._long_term_index),
            "experience": (self._experience_path, self._experience_index),
        }
        path, index = path_map.get(str(memory_type or "recent").strip().lower(), path_map["recent"])
        entry = self._prepare_memory_entry(entry, str(memory_type or "recent"))
        self._append_indexed_jsonl(path, index, entry)
        return entry

    def _looks_like_profile_payload(self, data) -> bool:
        return isinstance(data, dict) and bool(self.PROFILE_KEYS & set(data.keys())) and not bool(
            self.RECENT_KEYS & set(data.keys())
        )

    def _looks_like_recent_record(self, record: dict) -> bool:
        return bool(self.RECENT_KEYS & set(record.keys()))

    def _normalize_record(self, data):
        if isinstance(data, dict):
            record = dict(data)
        else:
            record = {"value": data}
        record.setdefault("timestamp", self._timestamp())
        return record

    def _store_profile(self, data: dict):
        with self._profile_lock:
            profile = dict(self._profile_cache or {})

            for key, value in data.items():
                if key == "facts" and isinstance(value, dict):
                    profile.setdefault("facts", {})
                    profile["facts"].update(value)
                elif key == "core_memory" and isinstance(value, list):
                    existing = profile.setdefault("core_memory", [])
                    existing.extend(value)
                else:
                    profile[key] = value

            self._profile_cache = profile
            self._refresh_profile_views_locked()
            self._save_json(self.profile_path, profile)
            self._rebuild_index()
            return profile

    def _profile_data(self):
        with self._profile_lock:
            return dict(self._profile_view)

    def _profile_candidates(self) -> list[dict]:
        with self._profile_lock:
            return [dict(item) for item in self._profile_candidates_cache]

    def _with_memory_type(self, entries: list[dict], memory_type: str) -> list[dict]:
        """Annotate in-memory copies so retrieval can weight sources without changing JSONL records."""
        annotated = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            item.setdefault("_memory_type", memory_type)
            annotated.append(item)
        return annotated

    def _get_all_entries(self) -> list[dict]:
        """Collect profile, short-term, long-term, and experience memories for budgeted retrieval."""
        candidates = (
            self._with_memory_type(self._profile_candidates(), "long_term")
            + self._with_memory_type(self._recent_index.entries(), "short_term")
            + self._with_memory_type(self._long_term_index.entries(), "long_term")
            + self._with_memory_type(self._experience_index.entries(), "experience")
        )
        return self._dedupe_records(candidates)

    def _rebuild_index(self):
        all_entries = self._get_all_entries()
        self._bm25_index.build(all_entries)
        logger.info("[MEMORY] Index built over %s entries", self._bm25_index.size)

    def _prepare_memory_entry(self, record: dict, memory_type: str) -> dict:
        entry = dict(record or {})
        normalized_type = str(memory_type or entry.get("memory_type") or entry.get("type") or "short_term").strip().lower()
        if normalized_type in {"recent", "short"}:
            normalized_type = "short_term"

        content = _memory_entry_text(entry)
        all_tags = set(str(tag) for tag in (entry.get("tags") or []) if tag)
        all_tags.update(auto_tag(content))
        entry["tags"] = sorted(all_tags)
        entry.setdefault("metadata", {})
        if not isinstance(entry["metadata"], dict):
            entry["metadata"] = {"value": entry["metadata"]}
        entry.setdefault("access_count", 0)
        entry.setdefault("timestamp", datetime.now().isoformat())
        entry.setdefault("memory_type", normalized_type)
        return entry

    def _prune_index(self, path: Path, attr_name: str, memory_type: str, max_recent: int) -> int:
        index = getattr(self, attr_name)
        entries = [self._prepare_memory_entry(entry, memory_type) for entry in index.entries()]
        kept, removed = prune_by_ttl(entries)
        if not removed:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for entry in kept:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        rebuilt = MemoryIndex(max_recent=max_recent)
        rebuilt.load_from_jsonl(path)
        setattr(self, attr_name, rebuilt)
        return removed

    def _match_score(self, item: dict, query_keywords: set[str]) -> int:
        record_keywords = self._extract_keywords(self._record_text(item))
        return len(query_keywords & record_keywords)

    def _rank_entries_by_relevance(self, query: str, entries: list[dict], top_k: int = 10) -> list[dict]:
        normalized_top_k = int(max(top_k or 0, 0))
        if normalized_top_k <= 0:
            return []
        if not entries:
            return []

        # Keep legacy callers on the same budgeted TF-IDF path as retrieve().
        return retrieve_relevant(str(query or ""), entries, limit=normalized_top_k)

    def _record_text(self, item: dict) -> str:
        if not isinstance(item, dict):
            return str(item)
        parts = []
        for key in ("type", "key", "value", "content", "user", "jarvis", "input", "output", "query", "response"):
            value = item.get(key)
            if value:
                parts.append(str(value))
        metadata = item.get("metadata")
        if isinstance(metadata, dict):
            parts.extend(str(value) for value in metadata.values() if value)
        if not parts:
            parts.extend(str(value) for value in item.values() if value)
        return " ".join(parts)

    def _extract_keywords(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9']+", text.lower())
        return {word for word in words if len(word) >= 3 and word not in self.STOPWORDS}

    def _read_jsonl(self, path: Path | str) -> list[dict]:
        index = self._index_for_path(path)
        if index is not None:
            return index.entries()

        source = Path(path)
        if not source.exists() or source.stat().st_size == 0:
            return []

        records = []
        with source.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                records.extend(self._parse_json_objects(line))
        return records

    def _append_indexed_jsonl(self, path: Path, index: MemoryIndex, record: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        index.add(record)
        if hasattr(self, "_bm25_index"):
            self._bm25_index.add(record)
        self._add_to_embedding_index(record)

    def _add_to_embedding_index(self, record: dict) -> None:
        try:
            self._embed_index.add(record)
        except Exception as exc:
            logger.debug("Embedding index add skipped (non-critical): %s", exc)
        try:
            self._persistent_index.add(record)
        except Exception as exc:
            logger.debug("Persistent embedding index add skipped (non-critical): %s", exc)

    def _load_profile_cache(self):
        with self._profile_lock:
            self._profile_cache = self._load_json(self.profile_path, {})
            self._refresh_profile_views_locked()

    def _refresh_profile_views_locked(self):
        profile = dict(self._profile_cache or {})
        raw_profile = {}

        if profile.get("name"):
            raw_profile["name"] = profile["name"]
        if isinstance(profile.get("core_memory"), list) and profile["core_memory"]:
            raw_profile["core_memory"] = list(profile["core_memory"])
        if isinstance(profile.get("facts"), dict) and profile["facts"]:
            raw_profile["facts"] = dict(profile["facts"])

        candidates = []
        if raw_profile.get("name"):
            candidates.append({"source": "profile", "type": "identity", "value": raw_profile["name"]})

        for item in raw_profile.get("core_memory", []):
            if isinstance(item, dict):
                candidate = {"source": "profile"}
                candidate.update(item)
                candidates.append(candidate)

        for key, value in raw_profile.get("facts", {}).items():
            candidates.append({"source": "profile", "key": key, "value": value})

        self._profile_view = raw_profile
        self._profile_candidates_cache = candidates

    def _load_json(self, path: Path, default):
        if not path.exists() or path.stat().st_size == 0:
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            # Profile JSON load failures are logged while preserving the supplied default.
            logger.debug("Could not load JSON from %s: %s", path, exc)
            return default

    def _save_json(self, path: Path, data):
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)

    def _parse_json_objects(self, text: str) -> list[dict]:
        decoder = json.JSONDecoder()
        records = []
        index = 0

        while index < len(text):
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                break

            try:
                value, next_index = decoder.raw_decode(text, index)
            except Exception as exc:
                # Malformed profile JSON stops parsing with debug context instead of failing startup.
                logger.debug("Stopped parsing profile JSON objects at offset %s: %s", index, exc)
                break

            if isinstance(value, dict):
                records.append(value)
            index = next_index

        return records

    def _load_index(self, index: MemoryIndex, paths: list[Path]):
        seen = set()
        for path in paths:
            resolved = str(Path(path))
            if resolved in seen:
                continue
            seen.add(resolved)
            index.load_from_jsonl(path)

    def _index_for_path(self, path: Path | str) -> MemoryIndex | None:
        candidate = str(Path(path))
        mapping = {
            str(self._recent_path): self._recent_index,
            str(self._long_term_path): self._long_term_index,
            str(self._experience_path): self._experience_index,
        }
        for legacy_path in self._legacy_recent_paths:
            mapping[str(legacy_path)] = self._recent_index
        for legacy_path in self._legacy_long_term_paths:
            mapping[str(legacy_path)] = self._long_term_index
        for legacy_path in self._legacy_experience_paths:
            mapping[str(legacy_path)] = self._experience_index
        return mapping.get(candidate)

    def _dedupe_records(self, records: list[dict]) -> list[dict]:
        seen = set()
        deduped = []
        for record in records:
            try:
                key = json.dumps(record, sort_keys=True, ensure_ascii=False)
            except TypeError:
                key = str(record)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped

    def _stringify_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        try:
            return json.dumps(content, ensure_ascii=False)
        except TypeError:
            return str(content)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "Memory",
    "MemoryIndex",
    "auto_tag",
    "compute_importance",
    "get_stats",
    "prune_by_ttl",
    "prune_stale_memories",
    "retrieve_bm25",
    "retrieve_relevant",
]
