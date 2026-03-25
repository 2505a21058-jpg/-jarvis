import ollama
import sqlite3
import json

# ------------------ Memory Setup ------------------
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_input TEXT,
    assistant_response TEXT,
    tags TEXT
)""")


# ------------------ Store Memory ------------------
def store_memory(user_input, assistant_response):
    text = user_input.lower().strip()

    if "my name is" in text:
        tag = "identity"
    elif "i like" in text and len(text) < 40:
        tag = "preference"
    else:
        return

    cursor.execute("SELECT user_input FROM memory")
    existing = [row[0].lower() for row in cursor.fetchall()]
    if text in existing:
        return

    cursor.execute(
        "INSERT INTO memory (user_input, assistant_response, tags) VALUES (?, ?, ?)",
        (user_input, assistant_response, tag)
    )
    conn.commit()


# ------------------ Retrieve Memory ------------------
def retrieve_memory(query):
    query = query.lower()

    cursor.execute("SELECT user_input, tags FROM memory")
    rows = cursor.fetchall()

    for u, tag in rows:
        if tag == "identity" and "name" in query:
            return [u]
        elif tag == "preference" and "what do i like" in query:
            return [u]

    return []


# ------------------ NORMALIZE TEXT ------------------
def normalize(text):
    text = text.lower()

    # normalize common variations
    text = text.replace("blocking", "block")
    text = text.replace("blocked", "block")
    text = text.replace("blocks", "block")

    return text


# ------------------ EXPERIENCE SEARCH (FINAL STABLE) ------------------
def search_experience(query):
    try:
        query = normalize(query)

        with open("training_data.jsonl", "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                prompt = normalize(data["prompt"])

                # VERY STRONG MATCH (guaranteed)
                if "pyaudio" in query and "pyaudio" in prompt:
                    if "block" in query and "block" in prompt:
                        return data["response"]

        return None

    except Exception as e:
        return None


# ------------------ PREPROCESS ------------------
def preprocess_input(text):
    return text


# ------------------ CHAT (SAFE) ------------------
def chat(user_input, personality_prompt):

    user_input = preprocess_input(user_input)

    system_message = f"""
{personality_prompt}

STRICT MODE:
- Max 2 sentences
- No guessing
"""

    try:
        response = ollama.chat(
            model="llama3.1",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_input}
            ],
            options={"temperature": 0.2}
        )

        reply = response["message"]["content"]

    except:
        reply = "Ollama not running."

    store_memory(user_input, reply)

    return reply