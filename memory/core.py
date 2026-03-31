import json
import datetime
import re
from pathlib import Path
from collections import deque

# Paths
MEMORY_DIR = Path("memory")
PROFILE_FILE = MEMORY_DIR / "user_profile.json"
EXPERIENCES_FILE = MEMORY_DIR / "experiences.jsonl"
STRUCTURED_FILE = MEMORY_DIR / "experiences.json"
RECENT_MEMORY_FILE = MEMORY_DIR / "memory.jsonl"
ARCHIVE_FILE = MEMORY_DIR / "memory_archive.jsonl"

MEMORY_DIR.mkdir(exist_ok=True)
PROFILE_FILE.touch(exist_ok=True)
EXPERIENCES_FILE.touch(exist_ok=True)
STRUCTURED_FILE.touch(exist_ok=True)
RECENT_MEMORY_FILE.touch(exist_ok=True)
ARCHIVE_FILE.touch(exist_ok=True)

# Short-term memory buffer
conversation_buffer = deque(maxlen=10)

# -----------------------------
# Conversation Context
# -----------------------------
def add_to_conversation(user_msg: str, jarvis_reply: str):
    conversation_buffer.append({
        "user": user_msg.strip()[:250],
        "jarvis": jarvis_reply.strip()[:350]
    })

def get_conversation_context() -> str:
    if not conversation_buffer:
        return ""
    text = "Recent conversation:\n"
    for turn in conversation_buffer:
        text += f"User: {turn['user']}\nJARVIS: {turn['jarvis']}\n"
    return text + "\n"

# -----------------------------
# Profile Management
# -----------------------------
def load_profile():
    if PROFILE_FILE.exists() and PROFILE_FILE.stat().st_size > 0:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"name": "Sir", "preferred_personality": "2", "home_city": "Hyderabad", "facts": {}}

def save_profile(profile):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=4, ensure_ascii=False)

def add_fact(key, value):
    profile = load_profile()
    profile["facts"][key] = value
    save_profile(profile)

def get_facts():
    profile = load_profile()
    return profile.get("facts", {})

# -----------------------------
# Experiences Management
# -----------------------------
def add_experience(memory_text: str):
    timestamp = datetime.datetime.now().strftime("%d-%b-%Y %H:%M")
    entry = {"timestamp": timestamp, "memory": memory_text.strip()}
    with open(EXPERIENCES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def get_recent_experiences(limit: int = 10):
    if not EXPERIENCES_FILE.exists():
        return []
    with open(EXPERIENCES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line.strip()) for line in lines]

# -----------------------------
# Experience Search (Cached)
# -----------------------------
def normalize(text: str) -> str:
    """Lowercase and strip punctuation for robust matching."""
    return re.sub(r"[^a-z0-9\s]", "", text.lower())

# Cache for structured experiences
_cached_experiences = []

def load_structured_experiences():
    """Preload and cache normalized tokens for experiences.json."""
    global _cached_experiences
    _cached_experiences = []
    if STRUCTURED_FILE.exists() and STRUCTURED_FILE.stat().st_size > 0:
        try:
            with open(STRUCTURED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    problem_tokens = normalize(item.get("problem", "")).split()
                    pattern_tokens = [normalize(p) for p in item.get("patterns", [])]
                    _cached_experiences.append({
                        "item": item,
                        "problem_tokens": problem_tokens,
                        "pattern_tokens": pattern_tokens
                    })
        except Exception:
            pass

# Load cache at startup
load_structured_experiences()

def search_experiences(query: str) -> str | None:
    """
    Search cached structured experiences first, then logs.
    Uses token overlap scoring to avoid brittle substring matches.
    """
    q_tokens = normalize(query).split()

    # 1. Cached structured experiences
    best_match = None
    best_score = 0
    for entry in _cached_experiences:
        problem_tokens = entry["problem_tokens"]
        pattern_tokens = entry["pattern_tokens"]

        # token overlap scoring
        score = len(set(q_tokens) & set(problem_tokens))
        for p in pattern_tokens:
            if p in normalize(query):
                score += 1

        if score > best_score:
            best_score = score
            best_match = entry["item"]

    if best_match and best_score >= 2:
        return f"{best_match.get('solution')} ({best_match.get('principle')})"

    # 2. Logs fallback (experiences.jsonl)
    if EXPERIENCES_FILE.exists() and EXPERIENCES_FILE.stat().st_size > 0:
        try:
            with open(EXPERIENCES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    item = json.loads(line)
                    memory_text = item.get("memory", "")
                    if any(word in normalize(memory_text) for word in q_tokens):
                        return memory_text
        except Exception:
            pass

    return None

# -----------------------------
# Auto-Promotion Pipeline
# -----------------------------
def promote_memories():
    """Promote high-importance memories into user_profile.json and rotate logs."""
    if RECENT_MEMORY_FILE.exists() and RECENT_MEMORY_FILE.stat().st_size > 0:
        with open(RECENT_MEMORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines[-500:]:  # keep last 500
            try:
                item = json.loads(line)
                importance = item.get("importance", 0)
                memory_text = item.get("memory", "")
                if importance >= 0.8:
                    add_fact(memory_text, memory_text)
                elif importance >= 0.5:
                    new_lines.append(line.strip())
            except Exception:
                continue

        # archive old entries
        with open(ARCHIVE_FILE, "a", encoding="utf-8") as archive:
            for line in lines[:-500]:
                archive.write(line)

        # overwrite with trimmed set
        with open(RECENT_MEMORY_FILE, "w", encoding="utf-8") as f:
            for line in new_lines:
                f.write(line + "\n")