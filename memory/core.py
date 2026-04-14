from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


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
    }

    def __init__(self, base_dir: str | Path = "memory"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.base_dir / "user_profile.json"
        self.memory_path = self.base_dir / "memory.jsonl"
        self.recent_path = self.base_dir / "recent_memories.jsonl"

    def store(self, data):
        if isinstance(data, list):
            return [self.store(item) for item in data]

        if self._looks_like_profile_payload(data):
            return self._store_profile(data)

        record = self._normalize_record(data)
        if self._looks_like_recent_record(record):
            self._append_jsonl(self.recent_path, record)
        else:
            self._append_jsonl(self.memory_path, record)
        return record

    def retrieve(self, query, mode="smart"):
        limits = self.MODE_LIMITS.get(mode, self.MODE_LIMITS["smart"])
        query_text = str(query or "")
        query_keywords = self._extract_keywords(query_text)
        profile = self._profile_data()
        recent_items = self.recent(limit=limits["recent"])
        memory_items = self._read_jsonl(self.memory_path)
        candidates = self._profile_candidates(profile) + memory_items

        if query_keywords:
            scored = []
            for item in candidates:
                score = self._match_score(item, query_keywords)
                if score <= 0:
                    continue
                scored.append((score, item))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            matches = [item for _, item in scored[: limits["matches"]]]
        else:
            matches = candidates[-limits["matches"] :]

        return {
            "profile": profile,
            "matches": matches,
            "recent": recent_items,
        }

    def recent(self, limit=5):
        if limit <= 0:
            return []
        items = self._read_jsonl(self.recent_path)
        return items[-int(limit) :]

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
        profile = self._load_json(self.profile_path, {})

        for key, value in data.items():
            if key == "facts" and isinstance(value, dict):
                profile.setdefault("facts", {})
                profile["facts"].update(value)
            elif key == "core_memory" and isinstance(value, list):
                existing = profile.setdefault("core_memory", [])
                existing.extend(value)
            else:
                profile[key] = value

        self._save_json(self.profile_path, profile)
        return profile

    def _profile_data(self):
        profile = self._load_json(self.profile_path, {})
        raw_profile = {}

        if profile.get("name"):
            raw_profile["name"] = profile["name"]
        if isinstance(profile.get("core_memory"), list) and profile["core_memory"]:
            raw_profile["core_memory"] = profile["core_memory"]
        if isinstance(profile.get("facts"), dict) and profile["facts"]:
            raw_profile["facts"] = profile["facts"]

        return raw_profile

    def _profile_candidates(self, profile: dict) -> list[dict]:
        candidates = []

        if profile.get("name"):
            candidates.append({"source": "profile", "type": "identity", "value": profile["name"]})

        for item in profile.get("core_memory", []):
            if isinstance(item, dict):
                candidate = {"source": "profile"}
                candidate.update(item)
                candidates.append(candidate)

        for key, value in profile.get("facts", {}).items():
            candidates.append({"source": "profile", "key": key, "value": value})

        return candidates

    def _match_score(self, item: dict, query_keywords: set[str]) -> int:
        record_keywords = self._extract_keywords(self._record_text(item))
        return len(query_keywords & record_keywords)

    def _record_text(self, item: dict) -> str:
        if not isinstance(item, dict):
            return str(item)
        parts = []
        for key in ("type", "key", "value", "user", "jarvis", "input", "output", "query", "response"):
            value = item.get(key)
            if value:
                parts.append(str(value))
        if not parts:
            parts.extend(str(value) for value in item.values() if value)
        return " ".join(parts)

    def _extract_keywords(self, text: str) -> set[str]:
        words = re.findall(r"[a-z0-9']+", text.lower())
        return {word for word in words if len(word) >= 3 and word not in self.STOPWORDS}

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists() or path.stat().st_size == 0:
            return []

        records = []
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                records.extend(self._parse_json_objects(line))
        return records

    def _append_jsonl(self, path: Path, record: dict):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _load_json(self, path: Path, default):
        if not path.exists() or path.stat().st_size == 0:
            return default
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
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
            except Exception:
                break

            if isinstance(value, dict):
                records.append(value)
            index = next_index

        return records

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = ["Memory"]
