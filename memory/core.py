import os
import json
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

PROFILE_FILE = "memory/profile.json"
EXPERIENCE_FILE = "memory/experiences.json"

embedder = None
index = None
stored_data = []


# ------------------ INIT ------------------
def init_embedding_model():
    global embedder, index, stored_data

    if embedder is None:
        embedder = SentenceTransformer("all-MiniLM-L6-v2")
        index = faiss.IndexFlatL2(384)
        stored_data = []

        if os.path.exists(EXPERIENCE_FILE):
            with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

                for item in data:
                    text = (
                        item.get("problem")
                        or item.get("memory")
                        or item.get("text")
                        or item.get("prompt")
                        or str(item)
                    )

                    vec = embedder.encode([text])[0]
                    index.add(np.array([vec]).astype("float32"))
                    stored_data.append(item)

    return embedder, index


# ------------------ PROFILE ------------------
def load_profile():
    if not os.path.exists(PROFILE_FILE):
        return {"name": "Sir", "facts": {}}

    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(profile):
    os.makedirs("memory", exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)


# ------------------ ADD EXPERIENCE ------------------
def add_experience(problem, solution):
    os.makedirs("memory", exist_ok=True)

    data = []
    if os.path.exists(EXPERIENCE_FILE):
        with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    if any(problem == d.get("problem") for d in data):
        return

    entry = {
        "problem": problem,
        "solution": solution
    }

    data.append(entry)

    with open(EXPERIENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    try:
        embedder, index = init_embedding_model()
        vec = embedder.encode([problem])[0]
        index.add(np.array([vec]).astype("float32"))
        stored_data.append(entry)
    except Exception as e:
        print("FAISS add error:", e)


# ------------------ GET FACTS ------------------
def get_all_facts():
    profile = load_profile()
    facts = profile.get("facts", {})

    exps = []
    if os.path.exists(EXPERIENCE_FILE):
        with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
            exps = json.load(f)

    return facts, exps


# ------------------ SEMANTIC SEARCH ------------------
def semantic_search(query, top_k=3):
    try:
        embedder, index = init_embedding_model()

        if index.ntotal == 0:
            return []

        query_vec = embedder.encode([query])[0]
        D, I = index.search(np.array([query_vec]).astype("float32"), top_k)

        results = []
        for idx in I[0]:
            if idx < len(stored_data):
                results.append(stored_data[idx])

        return results

    except Exception as e:
        print("Semantic search error:", e)
        return []