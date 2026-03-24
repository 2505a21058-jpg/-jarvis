import json
import sqlite3
import datetime
from pathlib import Path
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

MEMORY_DIR = Path("memory")
PROFILE_FILE = MEMORY_DIR / "user_profile.json"
EXPERIENCES_FILE = MEMORY_DIR / "experiences.jsonl"
DB_FILE = MEMORY_DIR / "memory.db"

# Create directory and files
MEMORY_DIR.mkdir(exist_ok=True)
PROFILE_FILE.touch(exist_ok=True)
EXPERIENCES_FILE.touch(exist_ok=True)

# Load embedding model (this may take a few seconds first time)
print("[Memory] Loading embedding model...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# FAISS index
dimension = 384  # dimension of all-MiniLM-L6-v2
index = faiss.IndexFlatL2(dimension)
experience_texts = []   # keep original texts for retrieval

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

def add_experience(text):
    """Add experience with embedding"""
    timestamp = datetime.datetime.now().strftime("%d-%b-%Y %H:%M")
    entry = {"timestamp": timestamp, "memory": text.strip()}
    
    # Save to JSONL
    with open(EXPERIENCES_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    
    # Add to FAISS
    embedding = embedder.encode([text])[0]
    index.add(np.array([embedding]).astype('float32'))
    experience_texts.append(text)

def get_recent_experiences(limit=8):
    if not EXPERIENCES_FILE.exists():
        return []
    with open(EXPERIENCES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line.strip()) for line in lines]

def semantic_search(query, top_k=3):
    """Find similar past experiences"""
    if len(experience_texts) == 0:
        return []
    query_emb = embedder.encode([query])[0]
    D, I = index.search(np.array([query_emb]).astype('float32'), top_k)
    results = []
    for i in I[0]:
        if i < len(experience_texts):
            results.append(experience_texts[i])
    return results

def get_all_facts():
    profile = load_profile()
    facts = profile.get("facts", {})
    experiences = get_recent_experiences(5)
    return facts, experiences

# Init DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""CREATE TABLE IF NOT EXISTS facts (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    added TEXT)""")
    conn.commit()
    conn.close()

init_db()