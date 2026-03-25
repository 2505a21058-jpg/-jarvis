# ------------------ Memory Setup ------------------
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_input TEXT,
    assistant_response TEXT,
    tags TEXT
)""")

# Lazy loading (FAST STARTUP)
model = None
index = None
dimension = 384

def get_model():
    global model
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
    return model

def get_index():
    global index
    if index is None:
        import faiss
        index = faiss.IndexFlatL2(dimension)
    return index


# ------------------ Store Memory ------------------
def store_memory(user_input, assistant_response, tags=""):
    text = user_input.lower().strip()

    # Only store meaningful info
    if "my name is" in text:
        tags = "identity"
    elif "i like" in text:
        tags = "preference"
    else:
        return

    # Prevent duplicates
    cursor.execute("SELECT user_input FROM memory")
    existing = [row[0].lower() for row in cursor.fetchall()]
    if text in existing:
        return

    cursor.execute(
        "INSERT INTO memory (user_input, assistant_response, tags) VALUES (?, ?, ?)",
        (user_input, assistant_response, tags)
    )
    conn.commit()

    embedding_model = get_model()
    faiss_index = get_index()

    embedding = embedding_model.encode([user_input])
    faiss_index.add(np.array(embedding, dtype=np.float32))


# ------------------ Retrieve Memory ------------------
def retrieve_memory(query, top_k=3):
    embedding_model = get_model()
    faiss_index = get_index()

    embedding = embedding_model.encode([query])
    D, I = faiss_index.search(np.array(embedding, dtype=np.float32), top_k)

    results = []
    for dist, idx in zip(D[0], I[0]):
        if dist > 1.5:
            continue

        cursor.execute("SELECT user_input, assistant_response, tags FROM memory WHERE id=?", (idx+1,))
        row = cursor.fetchone()

        if row:
            u, a, tag = row

            if tag == "identity" and "name" in query.lower():
                results.append((u, a))
            elif tag == "preference" and "like" in query.lower():
                results.append((u, a))

    return results


# ------------------ Chat Function ------------------
def chat(user_input, personality_prompt):
    past_context = retrieve_memory(user_input)

    # Only include relevant memory (fixes spam)
    relevant_context = []
    for u, a in past_context:
        if any(word in user_input.lower() for word in u.lower().split()):
            relevant_context.append(f"User: {u}\nAssistant: {a}")

    context_text = "\n".join(relevant_context)

    full_prompt = f"{personality_prompt}\n{context_text}\nUser: {user_input}\nAssistant:"

    conversation_history.append({"role": "user", "content": user_input})

    response = ollama.chat(
        model="llama3.2",
        messages=[{"role": "system", "content": personality_prompt}] + conversation_history
    )

    assistant_message = response["message"]["content"]

    conversation_history.append({"role": "assistant", "content": assistant_message})

    store_memory(user_input, assistant_message)

    return assistant_message