import json
import datetime
from pathlib import Path

MEMORY_DIR = Path("memory")
PROFILE_FILE = MEMORY_DIR / "user_profile.json"
EXPERIENCES_FILE = MEMORY_DIR / "experiences.jsonl"

MEMORY_DIR.mkdir(exist_ok=True)
PROFILE_FILE.touch(exist_ok=True)
EXPERIENCES_FILE.touch(exist_ok=True)

def load_profile():
    if PROFILE_FILE.exists() and PROFILE_FILE.stat().st_size > 0:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "name": "Sir",
        "preferred_personality": "2",
        "home_city": "Hyderabad",
        "facts": {}
    }

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

def add_experience(memory_text):
    timestamp = datetime.datetime.now().strftime("%d-%b-%Y %H:%M")
    entry = {
        "timestamp": timestamp,
        "memory": memory_text.strip()
    }
    with open(EXPERIENCES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def get_recent_experiences(limit=10):
    if not EXPERIENCES_FILE.exists():
        return []
    with open(EXPERIENCES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line.strip()) for line in lines]

def semantic_search(query, top_k=5):
    query_lower = query.lower()
    experiences = get_recent_experiences(30)
    results = []

    for exp in experiences:
        memory_lower = exp["memory"].lower()
        if query_lower in memory_lower or any(word in memory_lower for word in query_lower.split() if len(word) > 3):
            results.append(exp["memory"])

    return results[:top_k]