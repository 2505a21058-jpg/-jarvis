# memory/core.py
import json
import re
from datetime import datetime
from pathlib import Path
from collections import deque

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

USER_PROFILE_PATH = MEMORY_DIR / "user_profile.json"
RECENT_MEMORIES_PATH = MEMORY_DIR / "recent_memories.jsonl"
STRUCTURED_MEMORY_PATH = MEMORY_DIR / "memory.jsonl"

# Short-term conversation buffer
conversation_buffer = deque(maxlen=12)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our", "so",
    "that", "the", "this", "to", "was", "we", "what", "when", "where", "who",
    "why", "with", "you", "your"
}
USER_TRUNCATE_AT = 300
JARVIS_TRUNCATE_AT = 400
SUMMARY_MODEL_CANDIDATES = ("qwen3:8b", "llama3.2:3b")
ALLOWED_FACT_TYPES = {"identity", "role", "health", "preference"}
CORE_FACT_TYPES = {"identity", "role", "health"}
MAX_CORE_FACTS = 10
_memory_summary_done = False
_core_profile_block_cache = ""
_core_profile_loaded = False


def load_profile() -> dict:
    if USER_PROFILE_PATH.exists() and USER_PROFILE_PATH.stat().st_size > 0:
        try:
            with open(USER_PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"name": "Sir", "city": "Hyderabad", "facts": {}, "core_memory": []}


def _trim_message(text: str, max_len: int) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {word for word in words if len(word) >= 3 and word not in STOPWORDS}


def _normalize_fact_value(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _fact_keywords(value: str) -> set[str]:
    return _extract_keywords(value)


def _clean_fact_type(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned == "preferences":
        return "preference"
    return cleaned


def _clean_fact_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned.strip(" .,:;")


def _sanitize_fact(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    fact_type = _clean_fact_type(str(item.get("type", "")))
    fact_value = _clean_fact_value(str(item.get("value", "")))

    if fact_type not in ALLOWED_FACT_TYPES or not fact_value:
        return None

    if len(_normalize_fact_value(fact_value)) < 3:
        return None

    return {"type": fact_type, "value": fact_value}


def _build_core_profile_block(profile: dict) -> str:
    core_facts = []
    for fact in profile.get("core_memory", []):
        cleaned = _sanitize_fact(fact)
        if cleaned and cleaned["type"] in CORE_FACT_TYPES:
            core_facts.append(cleaned)

    identity_values = [fact["value"] for fact in core_facts if fact["type"] == "identity"]
    role_values = [fact["value"] for fact in core_facts if fact["type"] == "role"]
    health_values = [fact["value"] for fact in core_facts if fact["type"] == "health"]

    name_value = identity_values[0] if identity_values else ""
    if not name_value:
        fallback_name = str(profile.get("name", "")).strip()
        if fallback_name and fallback_name.lower() != "sir":
            name_value = fallback_name

    lines = ["User profile:"]
    if name_value:
        lines.append(f"Name: {name_value}")
    if role_values:
        lines.append(f"Role: {'; '.join(role_values)}")
    if health_values:
        lines.append(f"Health: {'; '.join(health_values)}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _set_core_profile_cache(profile: dict):
    global _core_profile_block_cache, _core_profile_loaded
    _core_profile_block_cache = _build_core_profile_block(profile)
    _core_profile_loaded = True


def get_core_profile_block() -> str:
    global _core_profile_loaded
    if not _core_profile_loaded:
        _set_core_profile_cache(load_profile())
    return _core_profile_block_cache


def _facts_are_similar(left: dict, right: dict) -> bool:
    if left.get("type") != right.get("type"):
        return False

    left_norm = _normalize_fact_value(left["value"])
    right_norm = _normalize_fact_value(right["value"])

    if not left_norm or not right_norm:
        return False

    if left_norm == right_norm:
        return True

    if left_norm in right_norm or right_norm in left_norm:
        return True

    left_keywords = _fact_keywords(left["value"])
    right_keywords = _fact_keywords(right["value"])

    if not left_keywords or not right_keywords:
        return False

    overlap = left_keywords & right_keywords
    return len(overlap) >= min(len(left_keywords), len(right_keywords))


def _prefer_fact(current: dict, candidate: dict) -> dict:
    current_score = (len(_fact_keywords(current["value"])), len(current["value"]))
    candidate_score = (len(_fact_keywords(candidate["value"])), len(candidate["value"]))
    return candidate if candidate_score > current_score else current


def _merge_facts(existing: list[dict], new_facts: list[dict]) -> list[dict]:
    merged = [fact.copy() for fact in existing]

    for raw_fact in new_facts:
        fact = _sanitize_fact(raw_fact)
        if not fact:
            continue

        replaced = False
        for index, existing_fact in enumerate(merged):
            if _facts_are_similar(existing_fact, fact):
                merged[index] = _prefer_fact(existing_fact, fact)
                replaced = True
                break

        if not replaced:
            merged.append(fact)

    return merged


def _load_structured_memory() -> list[dict]:
    if not STRUCTURED_MEMORY_PATH.exists() or STRUCTURED_MEMORY_PATH.stat().st_size == 0:
        return []

    facts = []
    try:
        with open(STRUCTURED_MEMORY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    fact = _sanitize_fact(json.loads(line))
                except Exception:
                    fact = None
                if fact:
                    facts.append(fact)
    except Exception:
        return []

    return facts


def _save_structured_memory(facts: list[dict]):
    with open(STRUCTURED_MEMORY_PATH, "w", encoding="utf-8") as f:
        for fact in facts:
            f.write(json.dumps(fact, ensure_ascii=True) + "\n")


def _save_profile(profile: dict):
    with open(USER_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    _set_core_profile_cache(profile)


def _format_recent_conversation_for_summary(limit: int = 10) -> str:
    turns = list(conversation_buffer)[-limit:]
    if not turns:
        return ""

    lines = []
    for turn in turns:
        lines.append(f"User: {turn['user']}")
        lines.append(f"Jarvis: {turn['jarvis']}")
    return "\n".join(lines)


def _extract_json_array(text: str) -> list:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []

    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return []

    return data if isinstance(data, list) else []


def _summarize_long_term_facts() -> list[dict]:
    conversation_text = _format_recent_conversation_for_summary(limit=10)
    if not conversation_text:
        return []

    prompt = f"""Extract only durable long-term user facts from this conversation.
Return ONLY a JSON array of objects with this exact schema:
[{{"type": "identity|role|health|preference", "value": "..."}}]

Rules:
- Keep only important long-term facts.
- Ignore temporary requests, greetings, tasks, one-off questions, and raw conversation.
- Allowed types: identity, role, health, preference.
- Preference means strong stable likes/dislikes only.
- If nothing important is present, return [].

Conversation:
{conversation_text}
"""

    try:
        import ollama
    except Exception:
        return []

    for model in SUMMARY_MODEL_CANDIDATES:
        try:
            response = ollama.chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract durable user facts and respond with JSON only."
                    },
                    {"role": "user", "content": prompt}
                ],
                options={"temperature": 0}
            )
            content = response["message"]["content"].strip()
            facts = _extract_json_array(content)
            if facts:
                return [fact for fact in (_sanitize_fact(item) for item in facts) if fact]
            if content == "[]":
                return []
        except Exception:
            continue

    return []


def summarize_and_store_long_term_memory():
    global _memory_summary_done
    if _memory_summary_done:
        return

    _memory_summary_done = True

    if not conversation_buffer:
        return

    new_facts = _summarize_long_term_facts()
    if not new_facts:
        return

    profile = load_profile()
    existing_core = []
    for fact in profile.get("core_memory", []):
        cleaned = _sanitize_fact(fact)
        if cleaned:
            existing_core.append(cleaned)

    core_facts = [fact for fact in new_facts if fact["type"] in CORE_FACT_TYPES]
    regular_facts = [fact for fact in new_facts if fact["type"] not in CORE_FACT_TYPES]

    merged_core = _merge_facts(existing_core, core_facts)[:MAX_CORE_FACTS]
    if merged_core:
        profile["core_memory"] = merged_core

        identity_fact = next((fact["value"] for fact in merged_core if fact["type"] == "identity"), None)
        if identity_fact:
            profile["name"] = identity_fact
    else:
        profile.setdefault("core_memory", [])

    _save_profile(profile)

    existing_regular = _load_structured_memory()
    merged_regular = _merge_facts(existing_regular, regular_facts)
    _save_structured_memory(merged_regular)


def get_conversation_context(limit: int = 6, user_query: str = "") -> str:
    if not conversation_buffer:
        return ""

    recent_turns = list(conversation_buffer)[-limit:]
    query_keywords = _extract_keywords(user_query)

    if query_keywords:
        filtered_turns = []
        for turn in recent_turns:
            turn_keywords = _extract_keywords(turn["user"] + " " + turn["jarvis"])
            if turn_keywords & query_keywords:
                filtered_turns.append(turn)
        recent_turns = filtered_turns

        if not recent_turns:
            recent_turns = list(conversation_buffer)[-2:]

    if not recent_turns:
        return ""

    lines = ["Recent context:"]
    for turn in recent_turns:
        lines.append(f"User: {turn['user']}")
        lines.append(f"Jarvis: {turn['jarvis']}")
    return "\n".join(lines)


def get_context_for_mode(mode: str, user_query: str = "") -> str:
    """Return different levels of context based on mode"""
    fast_base = get_conversation_context(limit=6, user_query=user_query)

    if mode == "fast":
        profile_block = get_core_profile_block()
        if profile_block and fast_base:
            return f"{profile_block}\n\n{fast_base}"
        if profile_block:
            return profile_block
        return fast_base

    elif mode == "smart":
        base = get_conversation_context(limit=6, user_query=user_query)
        from .promoter import get_important_memories
        important = get_important_memories(limit=15)
        return f"{base}\nImportant past memories:\n{important}"

    elif mode == "nerd":
        base = get_conversation_context(limit=6, user_query=user_query)
        from .promoter import get_important_memories
        important = get_important_memories(limit=30)
        return f"{base}\nAll relevant memories and experiences:\n{important}"

    return fast_base


def add_to_conversation(user_msg: str, jarvis_reply: str):
    conversation_buffer.append({
        "user": _trim_message(user_msg, USER_TRUNCATE_AT),
        "jarvis": _trim_message(jarvis_reply, JARVIS_TRUNCATE_AT)
    })

    # Save to file
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user_msg.strip(),
        "jarvis": jarvis_reply.strip(),
        "importance": 0.6
    }
    with open(RECENT_MEMORIES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def add_fact(key: str, value: str):
    profile = load_profile()
    profile.setdefault("facts", {})[key] = value
    _save_profile(profile)


def add_experience(experience: str):
    exp_path = MEMORY_DIR / "experiences.jsonl"
    with open(exp_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "timestamp": datetime.now().isoformat(),
            "experience": experience
        }) + "\n")
