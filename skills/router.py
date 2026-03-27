from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

print("✅ Final Hybrid Router Loaded")

def classify_difficulty(query: str) -> str:
    q = query.lower()
    if len(q.split()) <= 10 and any(g in q for g in ["hi", "hello", "hey", "how are you", "what's up"]):
        return "EASY"
    if any(word in q for word in ["calculate", "solve", "prove", "explain why", "how does", "latest", "current", "code", "program", "math", "physics", "difference"]):
        return "HARD"
    return "MEDIUM"

def handle_skill(query: str):
    q = query.lower().strip()

    # === Web Search / Browser Commands (Strong Trigger) ===
    if any(phrase in q for phrase in ["web search", "search for", "look up", "find on", "duckduckgo", "google search", "browse for", "search about"]):
        from .browser import browse
        return browse(query)

    # Open Apps (including Chrome)
    if any(w in q for w in ["open ", "launch ", "start "]):
        from .open_app import open_app
        return open_app(query)

    # PNR & Train
    if "pnr" in q or "train status" in q or "live train" in q:
        from .train import check_pnr, get_live_train
        import re
        pnr_match = re.search(r"\d{10}", q)
        if pnr_match:
            return check_pnr(pnr_match.group())
        train_match = re.search(r"\d{5}", q)
        if train_match:
            return get_live_train(train_match.group())
        return "Please provide a valid PNR or train number Sir."

    # Weather
    if "weather" in q:
        from .weather import get_weather
        city = q.replace("weather", "").strip() or "Hyderabad"
        return get_weather(city)

    # Date & Time
    if any(w in q for w in ["time", "date", "today", "now", "current time"]):
        from .datetime_skill import get_datetime
        return get_datetime()

    return None   # No skill matched → go to LLM

def process_query(query: str):
    """Main router"""
    skill_response = handle_skill(query)
    if skill_response:
        return skill_response, {"route": "skill"}

    difficulty = classify_difficulty(query)

    system_prompt = """You are JARVIS, a helpful, intelligent, and casual AI assistant.
Speak naturally like a smart friend.
Be accurate and useful.
Use user memories only when they are relevant.
Keep responses natural and concise."""

    try:
        if difficulty in ["HARD", "MEDIUM"]:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.3,
                max_tokens=700
            )
            response = completion.choices[0].message.content
            route = f"groq_{difficulty.lower()}"
        else:
            import ollama
            res = ollama.chat(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                options={"temperature": 0.3}
            )
            response = res["message"]["content"]
            route = "local_easy"

        return response, {"route": route, "difficulty": difficulty}

    except Exception as e:
        return f"Sorry, I had an issue: {str(e)}", {"route": "error"}