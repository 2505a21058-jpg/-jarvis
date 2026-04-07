# memory/core.py
import json
import math
import re
import threading
from datetime import datetime
from pathlib import Path
from collections import deque

from model_manager import SUMMARY_MODEL, ollama_chat

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

USER_PROFILE_PATH = MEMORY_DIR / "user_profile.json"
RECENT_MEMORIES_PATH = MEMORY_DIR / "recent_memories.jsonl"
STRUCTURED_MEMORY_PATH = MEMORY_DIR / "memory.jsonl"
CONVERSATION_SUMMARY_PATH = MEMORY_DIR / "conversation_summary.json"

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
SUMMARY_MODEL_CANDIDATES = (SUMMARY_MODEL,)
SUMMARY_TURN_LIMIT = 6
RECENT_CONTEXT_TURN_LIMIT = 3
SUMMARY_MIN_MESSAGE_COUNT = 8
SUMMARY_REFRESH_TURN_GAP = 3
SUMMARY_MAX_WORDS = 110
EMBEDDING_MODEL_CANDIDATES = ("nomic-embed-text", "mxbai-embed-large", "all-minilm")
ALLOWED_FACT_TYPES = {"identity", "role", "education", "health", "preference"}
CORE_FACT_TYPES = {"identity", "role", "health"}
MAX_CORE_FACTS = 10
_memory_summary_done = False
_core_profile_block_cache = ""
_core_profile_loaded = False
_conversation_summary_cache = ""
_conversation_summary_loaded = False
_summary_thread = None
_summary_lock = threading.Lock()
_conversation_turn_counter = 0
_last_summary_turn_counter = 0
DYNAMIC_TYPE_MAX_LENGTH = 20
SMART_MEMORY_LIMIT = 5
VECTOR_MEMORY_LIMIT = 3
NERD_MEMORY_LIMIT = 10
NERD_VECTOR_MEMORY_LIMIT = 5
MEMORY_SCAN_LIMIT = 50
DEFAULT_FACT_CONFIDENCE = 0.5
CONFIDENCE_STEP = 0.2
MIN_FACT_CONFIDENCE = 0.0
MAX_FACT_CONFIDENCE = 1.0
REJECTED_DYNAMIC_TYPES = {
    "data", "detail", "details", "fact", "facts", "general", "info",
    "information", "memory", "misc", "other", "profile", "stuff", "thing", "things"
}
FIRST_PERSON_MARKERS = {"i", "i'm", "im", "me", "my", "mine", "myself"}
THIRD_PARTY_MARKERS = {"friend", "friends", "he", "she", "they", "them", "their", "someone", "somebody"}
STRONG_CONFIDENCE_MARKERS = {"always", "definitely", "love"}
WEAK_CONFIDENCE_MARKERS = {"maybe", "perhaps"}
POSITIVE_SENTIMENT_MARKERS = {"like", "likes", "love", "loves", "prefer", "prefers"}
NEGATIVE_SENTIMENT_MARKERS = {"dislike", "dislikes", "hate", "hates", "avoid", "avoids"}
SENTIMENT_MARKERS = POSITIVE_SENTIMENT_MARKERS | NEGATIVE_SENTIMENT_MARKERS
SUMMARY_LOW_SIGNAL_MESSAGES = {
    "hi", "hello", "hey", "yo", "hi jarvis", "hello jarvis", "hey jarvis", "yo jarvis",
    "ok", "okay", "k", "kk", "cool", "nice", "sure", "yes", "yeah", "yep", "no", "nope",
    "thanks", "thank you", "thx", "sorry", "alright", "fine", "nothing", "ntg"
}
SUMMARY_SIGNAL_WORDS = {
    "allergy", "allergic", "college", "condition", "creator", "degree", "developer",
    "dislike", "education", "engineer", "founder", "hate", "health", "job", "like",
    "love", "name", "prefer", "preference", "role", "school", "semester", "student",
    "study", "studying", "university", "work", "working", "year"
}
NERD_REASONING_KEYWORDS = {
    "analyze", "architecture", "break", "bug", "compare", "debug", "deep",
    "design", "diagnose", "evaluate", "explain", "how", "optimize", "plan",
    "reason", "refactor", "solve", "step", "strategy", "tradeoff", "why"
}


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


def _fact_subject_keywords(value: str) -> set[str]:
    return {word for word in _fact_keywords(value) if word not in SENTIMENT_MARKERS}


def _clean_fact_type(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    if cleaned == "preferences":
        return "preference"
    return cleaned


def _clean_fact_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    return cleaned.strip(" .,:;")


def _clean_embedding(value) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None

    cleaned = []
    for item in value:
        if not isinstance(item, (int, float)):
            return None
        cleaned.append(float(item))
    return cleaned


def _clamp_confidence(value: float) -> float:
    return round(max(MIN_FACT_CONFIDENCE, min(MAX_FACT_CONFIDENCE, value)), 2)


def _clean_confidence(value) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return _clamp_confidence(float(value))


def _score_fact_confidence(text: str) -> float:
    lowered = text.lower()
    words = set(re.findall(r"[a-z']+", lowered))
    confidence = DEFAULT_FACT_CONFIDENCE

    if words & STRONG_CONFIDENCE_MARKERS:
        confidence += CONFIDENCE_STEP

    if "i think" in lowered or words & WEAK_CONFIDENCE_MARKERS:
        confidence -= CONFIDENCE_STEP

    return _clamp_confidence(confidence)


def _fact_confidence(fact: dict) -> float:
    confidence = _clean_confidence(fact.get("confidence"))
    return confidence if confidence is not None else DEFAULT_FACT_CONFIDENCE


def _fact_sentiment(value: str) -> int:
    words = set(re.findall(r"[a-z']+", value.lower()))
    has_positive = bool(words & POSITIVE_SENTIMENT_MARKERS)
    has_negative = bool(words & NEGATIVE_SENTIMENT_MARKERS)

    if has_positive and not has_negative:
        return 1
    if has_negative and not has_positive:
        return -1
    return 0


def _get_profile_name_keywords(profile: dict) -> set[str]:
    name = str(profile.get("name", "")).strip().lower()
    if not name or name == "sir":
        return set()
    return {part for part in re.findall(r"[a-z]+", name) if len(part) >= 2}


def _is_user_related_fact(fact_value: str, profile: dict) -> bool:
    lowered = fact_value.lower()
    words = set(re.findall(r"[a-z']+", lowered))

    if words & THIRD_PARTY_MARKERS:
        return False

    if words & FIRST_PERSON_MARKERS:
        return True

    name_keywords = _get_profile_name_keywords(profile)
    if name_keywords and name_keywords & words:
        return True

    return False


def _filter_user_related_facts(facts: list[dict], profile: dict) -> list[dict]:
    filtered = []
    for fact in facts:
        if _is_user_related_fact(fact["value"], profile):
            filtered.append(fact)
    return filtered


def _is_valid_dynamic_fact_type(fact_type: str) -> bool:
    if not fact_type:
        return False

    if fact_type in ALLOWED_FACT_TYPES or fact_type in REJECTED_DYNAMIC_TYPES:
        return False

    if len(fact_type) > DYNAMIC_TYPE_MAX_LENGTH:
        return False

    if not re.fullmatch(r"[a-z]+(?: [a-z]+)?", fact_type):
        return False

    words = fact_type.split()
    if len(words) > 2:
        return False

    return all(len(word) >= 2 for word in words)


def _sanitize_fact(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None

    fact_type = _clean_fact_type(str(item.get("type", "")))
    fact_value = _clean_fact_value(str(item.get("value", "")))

    if not fact_value:
        return None

    if fact_type not in ALLOWED_FACT_TYPES and not _is_valid_dynamic_fact_type(fact_type):
        return None

    if len(_normalize_fact_value(fact_value)) < 3:
        return None

    confidence = _clean_confidence(item.get("confidence"))
    fact = {
        "type": fact_type,
        "value": fact_value,
        "confidence": confidence if confidence is not None else _score_fact_confidence(fact_value),
    }
    embedding = _clean_embedding(item.get("embedding"))
    if embedding:
        fact["embedding"] = embedding
    return fact


def get_embedding(text: str) -> list[float]:
    text = _clean_fact_value(text)
    if not text:
        return []

    try:
        import ollama
    except Exception:
        return []

    for model in EMBEDDING_MODEL_CANDIDATES:
        try:
            response = ollama.embed(model=model, input=text)
            embeddings = response.get("embeddings") if isinstance(response, dict) else getattr(response, "embeddings", None)
            if embeddings and isinstance(embeddings, list) and embeddings[0]:
                embedding = _clean_embedding(embeddings[0])
                if embedding:
                    return embedding
        except Exception:
            pass

        try:
            response = ollama.embeddings(model=model, prompt=text)
            embedding = response.get("embedding") if isinstance(response, dict) else getattr(response, "embedding", None)
            embedding = _clean_embedding(embedding)
            if embedding:
                return embedding
        except Exception:
            continue

    return []


def cosine_similarity(vec1, vec2):
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot = sum(left * right for left, right in zip(vec1, vec2))
    norm1 = math.sqrt(sum(value * value for value in vec1))
    norm2 = math.sqrt(sum(value * value for value in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


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


def _trim_summary_words(text: str, max_words: int = SUMMARY_MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()

    remaining = max_words
    trimmed_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line_words = line.split()
        if not line_words:
            continue
        if len(line_words) <= remaining:
            trimmed_lines.append(line)
            remaining -= len(line_words)
            continue
        trimmed_lines.append(" ".join(line_words[:remaining]).strip())
        break

    return "\n".join(trimmed_lines).strip()


def _normalize_structured_summary(text: str) -> str:
    if not text:
        return ""

    sections = {
        "User Profile": [],
        "Recent Topics": [],
        "Preferences": [],
    }
    current_section = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized = line.rstrip(":").strip().lower()
        if normalized == "user profile":
            current_section = "User Profile"
            continue
        if normalized == "recent topics":
            current_section = "Recent Topics"
            continue
        if normalized == "preferences":
            current_section = "Preferences"
            continue

        if not current_section:
            continue

        value = line[1:].strip() if line.startswith("-") else line
        value = value.strip(" -")
        if value:
            sections[current_section].append(value)

    lines = ["User Profile:"]
    for value in (sections["User Profile"] or ["None"])[:2]:
        lines.append(f"- {value}")

    lines.append("Recent Topics:")
    for value in (sections["Recent Topics"] or ["None"])[:2]:
        lines.append(f"- {value}")

    preferences = [value for value in sections["Preferences"] if value.lower() != "none"]
    if preferences:
        lines.append("Preferences:")
        for value in preferences[:2]:
            lines.append(f"- {value}")

    return _trim_summary_words("\n".join(lines))


def _load_conversation_summary_data() -> dict:
    if not CONVERSATION_SUMMARY_PATH.exists() or CONVERSATION_SUMMARY_PATH.stat().st_size == 0:
        return {}

    try:
        with open(CONVERSATION_SUMMARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_conversation_summary_cache(data: dict):
    global _conversation_summary_cache, _conversation_summary_loaded
    summary = _normalize_structured_summary(str(data.get("summary", "")))
    _conversation_summary_cache = summary
    _conversation_summary_loaded = True


def get_conversation_summary_block() -> str:
    global _conversation_summary_loaded
    if not _conversation_summary_loaded:
        _set_conversation_summary_cache(_load_conversation_summary_data())
    return _conversation_summary_cache


def _save_conversation_summary(summary: str, source_turn_count: int):
    normalized_summary = _normalize_structured_summary(summary)
    if not normalized_summary:
        return

    data = {
        "summary": normalized_summary,
        "updated_at": datetime.now().isoformat(),
        "source_turn_count": source_turn_count,
    }
    with open(CONVERSATION_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    _set_conversation_summary_cache(data)


def _current_message_count() -> int:
    return len(conversation_buffer) * 2


def _should_schedule_conversation_summary() -> bool:
    if _current_message_count() <= SUMMARY_MIN_MESSAGE_COUNT:
        return False

    if _summary_thread is not None and _summary_thread.is_alive():
        return False

    if get_conversation_summary_block() and (_conversation_turn_counter - _last_summary_turn_counter) < SUMMARY_REFRESH_TURN_GAP:
        return False

    return True


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
    if len(overlap) >= min(len(left_keywords), len(right_keywords)):
        return True

    left_subject = _fact_subject_keywords(left["value"])
    right_subject = _fact_subject_keywords(right["value"])
    if not left_subject or not right_subject:
        return False

    subject_overlap = left_subject & right_subject
    return len(subject_overlap) >= min(len(left_subject), len(right_subject))


def _facts_contradict(left: dict, right: dict) -> bool:
    if left.get("type") != right.get("type"):
        return False

    left_sentiment = _fact_sentiment(left["value"])
    right_sentiment = _fact_sentiment(right["value"])
    if left_sentiment == 0 or right_sentiment == 0 or left_sentiment == right_sentiment:
        return False

    left_subject = _fact_subject_keywords(left["value"])
    right_subject = _fact_subject_keywords(right["value"])
    if not left_subject or not right_subject:
        return False

    return bool(left_subject & right_subject)


def _prefer_fact(current: dict, candidate: dict) -> dict:
    current_score = (len(_fact_keywords(current["value"])), len(current["value"]))
    candidate_score = (len(_fact_keywords(candidate["value"])), len(candidate["value"]))
    preferred = candidate if candidate_score > current_score else current
    fallback = current if preferred is candidate else candidate

    merged = preferred.copy()
    if "embedding" not in merged and "embedding" in fallback:
        merged["embedding"] = fallback["embedding"]
    if "confidence" not in merged:
        merged["confidence"] = _fact_confidence(fallback)
    return merged


def _merge_facts(existing: list[dict], new_facts: list[dict]) -> list[dict]:
    merged = [fact.copy() for fact in existing]

    for raw_fact in new_facts:
        fact = _sanitize_fact(raw_fact)
        if not fact:
            continue

        replaced = False
        for index, existing_fact in enumerate(merged):
            if _facts_are_similar(existing_fact, fact):
                if _facts_contradict(existing_fact, fact):
                    merged[index] = fact.copy()
                else:
                    merged_fact = _prefer_fact(existing_fact, fact)
                    merged_fact["confidence"] = _clamp_confidence(
                        max(_fact_confidence(existing_fact), _fact_confidence(fact)) + CONFIDENCE_STEP
                    )
                    merged[index] = merged_fact
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
        for raw_fact in facts:
            fact = _sanitize_fact(raw_fact)
            if not fact:
                continue
            if "embedding" not in fact:
                embedding = get_embedding(fact["value"])
                if embedding:
                    fact["embedding"] = embedding
            f.write(json.dumps(fact, ensure_ascii=True) + "\n")


def _save_profile(profile: dict):
    with open(USER_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    _set_core_profile_cache(profile)


def _join_context_blocks(*blocks: str) -> str:
    return "\n\n".join(block for block in blocks if block)


def _format_memory_block(title: str, facts: list[dict]) -> str:
    if not facts:
        return ""

    lines = [f"{title}:"]
    for fact in facts:
        lines.append(f"- {fact['type']}: {fact['value']}")
    return "\n".join(lines)


def _is_complex_nerd_query(query: str) -> bool:
    lowered = query.lower().strip()
    if not lowered:
        return False

    keywords = _extract_keywords(lowered)
    if keywords & NERD_REASONING_KEYWORDS:
        return True

    if len(lowered) >= 80:
        return True

    if lowered.count("?") > 1:
        return True

    if len(re.findall(r"\b(?:and|or|but|because|then|while)\b", lowered)) >= 2:
        return True

    return False


def _is_comparison_nerd_query(query: str) -> bool:
    lowered = query.lower().strip()
    if not lowered:
        return False

    comparison_patterns = (
        r"\bcompare\b",
        r"\bversus\b",
        r"\bvs\b",
        r"\bdifference between\b",
        r"\bbetter than\b",
        r"\bpros and cons\b",
        r"\bstrengths and weaknesses\b",
    )
    return any(re.search(pattern, lowered) for pattern in comparison_patterns)


def _get_nerd_instruction_block(query: str = "") -> str:
    lines = [
        "Nerd mode instructions:",
        "- Prefer structured answers with headings or numbered steps when helpful.",
        "- Give deeper explanations and include important details.",
        "- Prioritize accuracy and clarity over speed.",
        "- Longer answers are allowed when they improve understanding.",
        "- Explain why each concept works, not just what it is.",
        "- Prefer analysis over description.",
        "- Include meaningful tradeoffs with reasoning when relevant.",
        "- Avoid generic statements and unsupported claims.",
    ]

    if _is_complex_nerd_query(query):
        lines.extend([
            "- Think step by step before answering.",
            "- Break the problem into parts internally before writing the final answer.",
            "- Do not expose raw chain-of-thought. Provide only a clean, structured final answer.",
        ])

    if _is_comparison_nerd_query(query):
        lines.extend([
            "- For comparison questions, explicitly analyze strengths vs weaknesses.",
            "- Explain real-world implications and when each approach is the better choice.",
            "- Do not stop at listing differences; explain the consequences of those differences.",
        ])

    return "\n".join(lines)


def _normalize_summary_message(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _is_meaningful_summary_user_message(text: str) -> bool:
    normalized = _normalize_summary_message(text)
    if not normalized or normalized in SUMMARY_LOW_SIGNAL_MESSAGES:
        return False

    words = normalized.split()
    if "test" in words or "tests" in words:
        return False

    if len(words) >= 4:
        return True

    if set(words) & SUMMARY_SIGNAL_WORDS:
        return True

    if set(words) & FIRST_PERSON_MARKERS:
        if _extract_keywords(normalized) or re.search(r"\d", normalized):
            return True

    return False


def _get_summary_turns(limit: int = SUMMARY_TURN_LIMIT) -> list[dict]:
    turns = list(conversation_buffer)[-limit:]
    if not turns:
        return []

    filtered_turns = []
    for turn in turns:
        user_text = turn.get("user", "").strip()
        if not _is_meaningful_summary_user_message(user_text):
            continue
        filtered_turns.append(turn)
    return filtered_turns


def _format_recent_conversation_for_summary(limit: int = SUMMARY_TURN_LIMIT) -> str:
    turns = _get_summary_turns(limit=limit)
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


def _summarize_conversation_overview() -> str:
    conversation_text = _format_recent_conversation_for_summary(limit=SUMMARY_TURN_LIMIT)
    if not conversation_text:
        return ""

    prompt = f"""Summarize this conversation in under 150 tokens.
Return ONLY this format:
User Profile:
- ...
Recent Topics:
- ...
Preferences:
- ...  (only if clear)

Rules:
- Keep it short, concrete, and useful for continuity.
- Focus on stable user info, active topics, and clear preferences.
- Do not include greetings, filler, or raw dialogue.
- If a section has nothing clear, use - None.

Conversation:
{conversation_text}
"""

    try:
        import ollama
    except Exception:
        return ""

    for model in SUMMARY_MODEL_CANDIDATES:
        try:
            response = ollama_chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You create short structured conversation summaries."
                    },
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0,
                    "num_predict": 140,
                }
            )
            content = response["message"]["content"].strip()
            summary = _normalize_structured_summary(content)
            if summary:
                return summary
        except Exception:
            continue

    return ""


def _conversation_summary_worker(source_turn_count: int):
    global _summary_thread, _last_summary_turn_counter

    try:
        summary = _summarize_conversation_overview()
        if summary:
            _save_conversation_summary(summary, source_turn_count)
    finally:
        with _summary_lock:
            _last_summary_turn_counter = max(_last_summary_turn_counter, source_turn_count)
            _summary_thread = None


def maybe_schedule_conversation_summary():
    global _summary_thread

    with _summary_lock:
        if not _should_schedule_conversation_summary():
            return

        source_turn_count = _conversation_turn_counter
        _summary_thread = threading.Thread(
            target=_conversation_summary_worker,
            args=(source_turn_count,),
            daemon=True,
        )
        _summary_thread.start()


def _summarize_long_term_facts() -> list[dict]:
    conversation_text = _format_recent_conversation_for_summary(limit=SUMMARY_TURN_LIMIT)
    if not conversation_text:
        return []

    prompt = f"""Extract only durable long-term user facts from this conversation.
Return ONLY a strict JSON array of objects with this schema:
[{{"type": "identity|role|education|health|preference|custom", "value": "..."}}]

Classification rules:
- identity = ONLY the person's name. Never use identity for university, degree, role, status, or biography.
- role = the user's role or function, such as creator, student, developer, engineer, founder, or job title.
- education = degree, branch, university, school, academic year, semester, or study status.
- health = allergies, medical conditions, dietary restrictions, or health-related facts.
- preference = strong stable likes or dislikes only.
- You may create a new meaningful type when needed if none of the core types fit well, for example interest, subject, or goal.
- Avoid vague, redundant, overlapping, or duplicate types.

Extraction rules:
- Keep only important long-term facts.
- Ignore temporary requests, greetings, tests, one-off tasks, and raw conversation.
- Do NOT misclassify education as identity.
- If a new fact contradicts an older one, return only the latest correct fact.
- Return no duplicates.
- Return no conflicting facts.
- Return no explanation or extra text.
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
            response = ollama_chat(
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

    print("[Memory] Summarization started")

    try:
        _memory_summary_done = True

        if not conversation_buffer:
            return

        summary_turns = _get_summary_turns(limit=SUMMARY_TURN_LIMIT)
        print(f"[Memory] Processing {len(summary_turns)} conversation turns")

        if not summary_turns:
            return

        new_facts = _summarize_long_term_facts()
        print("[Memory] Extracted facts:", new_facts)
        if not new_facts:
            return

        profile = load_profile()
        new_facts = _filter_user_related_facts(new_facts, profile)
        print("[Memory] User-related facts:", new_facts)
        if not new_facts:
            return

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

        print("[Memory] Saving to profile and memory store")
        _save_profile(profile)

        existing_regular = _load_structured_memory()
        merged_regular = _merge_facts(existing_regular, regular_facts)
        _save_structured_memory(merged_regular)
        print("[Memory] Memory saved successfully")
    except Exception as e:
        print("[Memory] Error:", e)


def get_conversation_context(limit: int = RECENT_CONTEXT_TURN_LIMIT, user_query: str = "") -> str:
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


def _get_keyword_memory_matches(query: str, limit: int = SMART_MEMORY_LIMIT) -> list[dict]:
    query_keywords = _extract_keywords(query)
    if not query_keywords:
        return []

    memories = _load_structured_memory()[-MEMORY_SCAN_LIMIT:]
    if not memories:
        return []

    scored_memories = []
    for fact in memories:
        confidence = _fact_confidence(fact)
        if confidence < DEFAULT_FACT_CONFIDENCE:
            continue
        fact_keywords = _extract_keywords(f"{fact['type']} {fact['value']}")
        overlap = fact_keywords & query_keywords
        if overlap:
            similarity = float(len(overlap))
            final_score = similarity + confidence
            scored_memories.append((final_score, similarity, len(fact_keywords), fact))

    if not scored_memories:
        return []

    scored_memories.sort(key=lambda item: (item[0], item[1], item[2], len(item[3]["value"])), reverse=True)
    return [fact for _, _, _, fact in scored_memories[:limit]]


def _get_vector_memory_matches(query: str, limit: int = VECTOR_MEMORY_LIMIT) -> list[dict]:
    query_embedding = get_embedding(query)
    if not query_embedding:
        return []

    memories = _load_structured_memory()[-MEMORY_SCAN_LIMIT:]
    if not memories:
        return []

    scored_memories = []
    for fact in memories:
        confidence = _fact_confidence(fact)
        if confidence < DEFAULT_FACT_CONFIDENCE:
            continue
        embedding = _clean_embedding(fact.get("embedding"))
        if not embedding:
            continue
        similarity = cosine_similarity(query_embedding, embedding)
        if similarity > 0:
            final_score = similarity + confidence
            scored_memories.append((final_score, similarity, fact))

    if not scored_memories:
        return []

    scored_memories.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [fact for _, _, fact in scored_memories[:limit]]


def _merge_memory_matches(*fact_lists: list[dict], limit: int = SMART_MEMORY_LIMIT) -> list[dict]:
    merged = []
    for facts in fact_lists:
        for fact in facts:
            if any(_facts_are_similar(existing, fact) for existing in merged):
                continue
            merged.append(fact)
            if len(merged) >= limit:
                return merged
    return merged


def get_smart_memory_context(
    query: str,
    limit: int = SMART_MEMORY_LIMIT,
    vector_limit: int = VECTOR_MEMORY_LIMIT,
) -> str:
    keyword_matches = _get_keyword_memory_matches(query, limit=limit)
    vector_matches = _get_vector_memory_matches(query, limit=vector_limit)
    merged_matches = _merge_memory_matches(keyword_matches, vector_matches, limit=limit)
    return _format_memory_block("Relevant memory", merged_matches)


def get_vector_memory_context(query: str) -> str:
    vector_matches = _get_vector_memory_matches(query, limit=VECTOR_MEMORY_LIMIT)
    return _format_memory_block("Semantic memory", vector_matches)


def get_context_for_mode(mode: str, user_query: str = "") -> str:
    """Return different levels of context based on mode"""
    fast_base = get_conversation_context(limit=RECENT_CONTEXT_TURN_LIMIT, user_query=user_query)
    conversation_summary = get_conversation_summary_block()

    if mode == "fast":
        profile_block = get_core_profile_block()
        if profile_block and fast_base:
            return f"{profile_block}\n\n{fast_base}"
        if profile_block:
            return profile_block
        return fast_base

    elif mode == "smart":
        profile_block = get_core_profile_block()
        smart_memory = get_smart_memory_context(user_query)
        recent_context = get_conversation_context(limit=RECENT_CONTEXT_TURN_LIMIT, user_query=user_query)
        return _join_context_blocks(profile_block, conversation_summary, smart_memory, recent_context)

    elif mode == "nerd":
        profile_block = get_core_profile_block()
        smart_memory = get_smart_memory_context(
            user_query,
            limit=NERD_MEMORY_LIMIT,
            vector_limit=NERD_VECTOR_MEMORY_LIMIT,
        )
        recent_context = get_conversation_context(limit=RECENT_CONTEXT_TURN_LIMIT, user_query=user_query)
        nerd_instructions = _get_nerd_instruction_block(user_query)
        return _join_context_blocks(nerd_instructions, profile_block, conversation_summary, smart_memory, recent_context)

    return fast_base


def add_to_conversation(user_msg: str, jarvis_reply: str):
    global _conversation_turn_counter

    conversation_buffer.append({
        "user": _trim_message(user_msg, USER_TRUNCATE_AT),
        "jarvis": _trim_message(jarvis_reply, JARVIS_TRUNCATE_AT)
    })
    _conversation_turn_counter += 1

    # Save to file
    entry = {
        "timestamp": datetime.now().isoformat(),
        "user": user_msg.strip(),
        "jarvis": jarvis_reply.strip(),
        "importance": 0.6
    }
    with open(RECENT_MEMORIES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    maybe_schedule_conversation_summary()


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
