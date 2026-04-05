# memory/promoter.py
import json
from pathlib import Path

RECENT_MEMORIES_FILE = Path("memory/recent_memories.jsonl")

def get_important_memories(limit: int = 15) -> str:
    """Return important recent memories for Smart and Nerd modes"""
    if not RECENT_MEMORIES_FILE.exists():
        return "No recent memories available."

    try:
        with open(RECENT_MEMORIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]

        memories = []
        for line in lines:
            try:
                item = json.loads(line.strip())
                user_msg = item.get("user", "")
                jarvis_reply = item.get("jarvis", "")
                if user_msg or jarvis_reply:
                    memories.append(f"User: {user_msg}\nJARVIS: {jarvis_reply}")
            except:
                continue

        return "\n\n".join(memories) if memories else "No important memories yet."

    except Exception:
        return "No important memories available."


def promote_memories():
    """Can be expanded later"""
    pass


if __name__ == "__main__":
    promote_memories()
    print("✅ Memory promoter ready")