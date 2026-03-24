import ollama
from rich.console import Console
import sqlite3
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

console = Console()

# ------------------ Personalities ------------------
PERSONALITIES = {
    "1": {"name": "Normal", "prompt": "You are JARVIS, a helpful and efficient personal AI assistant. You are clear, direct and friendly. Keep responses concise. Your responses will be spoken out loud by Edge TTS Christopher Neural voice. No asterisks, no action text, no markdown, no emojis."},
    "2": {"name": "JARVIS", "prompt": "You are JARVIS, the sophisticated AI from Iron Man. Always address user as Sir. Be calm, precise, with dry wit. Your responses will be spoken out loud by Edge TTS Christopher Neural voice. No asterisks, no action text, no markdown, no emojis. Pure spoken English only."},
    "3": {"name": "Funny", "prompt": "You are JARVIS, an intelligent but meme-obsessed AI. You know every meme. Use Gen-Z slang naturally. Call user bestie. Say no cap when appropriate. Your responses will be spoken out loud by Edge TTS Christopher Neural voice. No asterisks, no action text, no markdown, no emojis. Say for real instead of fr fr."},
    "4": {"name": "Desi", "prompt": "You are JARVIS but make it desi. You speak in Hinglish naturally mixing Hindi and English. You make Bollywood references, cricket references. You say things like arre yaar, bas kar yaar, ekdum mast. You are helpful but very Indian in your vibe. Your responses will be spoken out loud by Edge TTS Christopher Neural voice. No asterisks, no action text, no markdown, no emojis."}
}

conversation_history = []

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

model = SentenceTransformer("all-MiniLM-L6-v2")
dimension = 384
index = faiss.IndexFlatL2(dimension)

def store_memory(user_input, assistant_response, tags=""):
    cursor.execute("INSERT INTO memory (user_input, assistant_response, tags) VALUES (?, ?, ?)",
                   (user_input, assistant_response, tags))
    conn.commit()
    embedding = model.encode([user_input])
    index.add(np.array(embedding, dtype=np.float32))

def retrieve_memory(query, top_k=3):
    embedding = model.encode([query])
    D, I = index.search(np.array(embedding, dtype=np.float32), top_k)
    results = []
    for idx in I[0]:
        cursor.execute("SELECT user_input, assistant_response FROM memory WHERE id=?", (idx+1,))
        row = cursor.fetchone()
        if row:
            results.append(row)
    return results

# ------------------ Personality Choice ------------------
def get_personality_choice():
    while True:
        raw = input("Enter choice (1/2/3/4 or normal/jarvis/funny/desi): ").strip().lower()
        if raw in ["1", "normal"]: return "1"
        elif raw in ["2", "jarvis", "iron man"]: return "2"
        elif raw in ["3", "funny", "meme"]: return "3"
        elif raw in ["4", "desi", "hindi", "hinglish"]: return "4"
        else: print("Invalid, try again")

# ------------------ Chat Function ------------------
def chat(user_input, personality_prompt):
    # Retrieve past context
    past_context = retrieve_memory(user_input)
    context_text = "\n".join([f"User: {u}\nAssistant: {a}" for u, a in past_context])

    # Build full prompt with personality + memory
    full_prompt = f"{personality_prompt}\n{context_text}\nUser: {user_input}\nAssistant:"

    # Append to conversation history
    conversation_history.append({"role": "user", "content": user_input})
    response = ollama.chat(model="llama3.2", messages=[{"role": "system", "content": personality_prompt}] + conversation_history)
    assistant_message = response["message"]["content"]
    conversation_history.append({"role": "assistant", "content": assistant_message})

    # Store memory
    store_memory(user_input, assistant_message)

    return assistant_message