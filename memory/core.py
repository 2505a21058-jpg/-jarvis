from __future__ import annotations

import collections
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from memory.embeddings import EmbeddingIndex
from memory.scorer import TFIDFScorer


logger = logging.getLogger("jarvis.memory.core")


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
            indices = list(range(len(self._entries)))
            ranked = self._scorer.rank(query_text, indices, top_k=normalized_limit)
            if ranked:
                return [self._entries[idx] for idx, _ in ranked]

            keyword_lower = query_text.lower()
            matches = [entry for entry in self._entries if keyword_lower in self._entry_text(entry)]

        return matches[-normalized_limit:]

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
        self._embed_index = EmbeddingIndex(max_entries=1000)

        self._profile_lock = Lock()
        self._profile_cache: dict[str, Any] = {}
        self._profile_view: dict[str, Any] = {}
        self._profile_candidates_cache: list[dict[str, Any]] = []
        self._load_profile_cache()

        self._load_index(self._recent_index, [self._recent_path, *self._legacy_recent_paths])
        self._load_index(self._long_term_index, [self._long_term_path, *self._legacy_long_term_paths])
        self._load_index(self._experience_index, [self._experience_path, *self._legacy_experience_paths])

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
            self._append_indexed_jsonl(self._recent_path, self._recent_index, record)
        else:
            self._append_indexed_jsonl(self._long_term_path, self._long_term_index, record)
        return record

    def retrieve(self, query, mode="smart", limit: int | None = None):
        mode_name = str(mode or "smart").strip().lower()
        default_limit = int(limit or 10)
        query_text = str(query or "")

        if mode_name == "recent":
            return self._recent_index.recent(default_limit)

        if mode_name == "semantic":
            results = self._embed_index.search(query_text, top_k=default_limit)
            if not results:
                return self._recent_index.search_by_keyword(query_text, limit=default_limit)
            return results

        if mode_name == "tags":
            tags = query if isinstance(query, list) else str(query or "").split()
            candidates = (
                self._recent_index.search_by_tags(tags)
                + self._long_term_index.search_by_tags(tags)
                + self._experience_index.search_by_tags(tags)
            )
            deduped = self._dedupe_records(candidates)
            ranked = self._rank_entries_by_relevance(" ".join(str(tag) for tag in tags), deduped, top_k=default_limit)
            if ranked:
                return ranked
            return deduped[:default_limit]

        if mode_name == "deep":
            results = self._recent_index.search_by_keyword(query_text, limit=default_limit)
            deep = self._long_term_index.search_by_keyword(query_text, limit=default_limit)
            combined = self._dedupe_records(results + deep)
            ranked = self._rank_entries_by_relevance(query_text, combined, top_k=default_limit)
            if not ranked:
                semantic = self._embed_index.search(query_text, top_k=default_limit)
                if semantic:
                    logger.debug("TF-IDF miss (deep) - semantic fallback returned %s results", len(semantic))
                    return semantic
            return ranked

        if mode_name == "fast" and query_text.strip():
            results = self._recent_index.search_by_keyword(query_text, limit=default_limit)
            if not results:
                semantic = self._embed_index.search(query_text, top_k=default_limit)
                if semantic:
                    logger.debug("TF-IDF miss - semantic fallback returned %s results", len(semantic))
                    return semantic
            return results

        limits = self.MODE_LIMITS.get(mode_name, self.MODE_LIMITS["smart"])
        query_keywords = self._extract_keywords(query_text)
        profile = self._profile_data()
        recent_items = self.recent(limit=limits["recent"])
        memory_items = self._long_term_index.entries()
        candidates = self._profile_candidates() + memory_items

        if query_keywords:
            matches = self._rank_entries_by_relevance(query_text, candidates, top_k=limits["matches"])
        else:
            matches = candidates[-limits["matches"] :]

        if query_keywords and not matches:
            semantic = self._embed_index.search(query_text, top_k=limits["matches"])
            if semantic:
                logger.debug("TF-IDF miss (%s) - semantic fallback returned %s results", mode_name, len(semantic))
                matches = semantic

        return {
            "profile": profile,
            "matches": matches,
            "recent": recent_items,
        }

    def recent(self, limit=5, n: int | None = None):
        count = int(n if n is not None else limit)
        if count <= 0:
            return []
        return self._recent_index.recent(count)

    def store_experience(self, content: str, tags: list[str] | None = None) -> None:
        """Stores to experience memory. Called by agent/learn.py."""
        self.store(content=content, tags=tags or [], memory_type="experience")

    def prune_experiences(self, max_entries: int = 1000) -> None:
        entries = self._experience_index.recent(max_entries)
        self._experience_path.parent.mkdir(parents=True, exist_ok=True)
        with self._experience_path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        self._experience_index = MemoryIndex(max_recent=500)
        self._experience_index.load_from_jsonl(self._experience_path)

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
        return self._embed_index.is_available()

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
            "long_term": (self._long_term_path, self._long_term_index),
            "experience": (self._experience_path, self._experience_index),
        }
        path, index = path_map.get(str(memory_type or "recent").strip().lower(), path_map["recent"])
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
            return profile

    def _profile_data(self):
        with self._profile_lock:
            return dict(self._profile_view)

    def _profile_candidates(self) -> list[dict]:
        with self._profile_lock:
            return [dict(item) for item in self._profile_candidates_cache]

    def _match_score(self, item: dict, query_keywords: set[str]) -> int:
        record_keywords = self._extract_keywords(self._record_text(item))
        return len(query_keywords & record_keywords)

    def _rank_entries_by_relevance(self, query: str, entries: list[dict], top_k: int = 10) -> list[dict]:
        normalized_top_k = int(max(top_k or 0, 0))
        if normalized_top_k <= 0:
            return []
        if not entries:
            return []

        scorer = TFIDFScorer()
        prepared_entries = []
        for entry in entries:
            record_text = self._record_text(entry)
            scorer.add(record_text)
            prepared_entries.append({"entry": entry, "content": record_text})

        ranked = scorer.rank_entries(str(query or ""), prepared_entries, top_k=normalized_top_k)
        if ranked:
            return [item["entry"] for item in ranked]

        query_lower = str(query or "").lower().strip()
        if not query_lower:
            return entries[-normalized_top_k:]

        fallback = [entry for entry in entries if query_lower in self._record_text(entry).lower()]
        return fallback[-normalized_top_k:]

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
        self._add_to_embedding_index(record)

    def _add_to_embedding_index(self, record: dict) -> None:
        try:
            self._embed_index.add(record)
        except Exception as exc:
            logger.debug("Embedding index add skipped (non-critical): %s", exc)

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


__all__ = ["Memory", "MemoryIndex"]
