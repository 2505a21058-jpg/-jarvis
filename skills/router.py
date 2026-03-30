from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

print("✅ Final Hybrid Router Loaded")

def classify_difficulty(query: str) -> str:
    q = query.lower()
    if len(q.split()) <= 10 and any(g in q for g in ["hi", "hello", "hey", "how are you", "what's up", "all gud"]):
        return "EASY"
    if any(word in q for word in ["calculate", "solve", "prove", "explain why", "how does", "latest", "current", "code", "program", "math", "physics", "difference"]):
        return "HARD"
    return "MEDIUM"

def handle_skill(query: str):
    q = query.lower().strip()

    # Web Search / Browser
    if any(phrase in q for phrase in ["web search", "search for", "look up", "find on", "duckduckgo", "google search", "browse for", "search about"]):
        try:
            from .browser import browse
            return browse(query)
        except Exception as e:
            return f"Browser skill failed: {str(e)}"

    # Open Apps
    if any(w in q for w in ["open ", "launch ", "start "]):
        try:
            from .open_app import open_app
            return open_app(query)
        except Exception as e:
            return f"Open app failed: {str(e)}"

    # PNR & Train
    if "pnr" in q or "train status" in q or "live train" in q:
        try:
            from .train import check_pnr, get_live_train
            import re
            pnr_match = re.search(r"\d{10}", q)
            if pnr_match:
                return check_pnr(pnr_match.group())
            train_match = re.search(r"\d{5}", q)
            if train_match:
                return get_live_train(train_match.group())
            return "Please provide a valid PNR or train number Sir."
        except Exception as e:
            return f"Train skill error: {str(e)}"

    # Weather
    if "weather" in q:
        try:
            from .weather import get_weather
            city = q.replace("weather", "").strip() or "Hyderabad"
            return get_weather(city)
        except Exception as e:
            return f"Weather skill failed: {str(e)}"

    # Date & Time
    if any(w in q for w in ["time", "date", "today", "now", "current time"]):
        try:
            from .datetime_skill import get_datetime
            return get_datetime()
        except Exception as e:
            return f"Datetime skill failed: {str(e)}"

    return None   # No skill matched → go to LLM

def process_query(full_prompt: str):
    """Main router - now accepts full prompt from jarvis.py (history + memory + rules)"""
    skill_response = handle_skill(full_prompt)   # Note: we still check skills on the original input if needed
    if skill_response:
        return skill_response, {"route": "skill"}

    system_prompt = """You are JARVIS, a helpful, intelligent, and casual AI assistant.
Speak naturally like a smart friend.
Be accurate and useful.

Important Rules:
- Only use memories if they are directly relevant to the current message.
- Do NOT force old facts (like food preferences, potatoes, Venkatesh) into casual greetings.
- Do NOT use the user's full name in every reply. Use "Sir" for casual messages.
- Continue the conversation naturally based on previous messages."""

    try:
        # Prefer Groq for better reasoning
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.35,
            max_tokens=800
        )
        response = completion.choices[0].message.content
        route = "groq"

        return response, {"route": route}

    except Exception as e:
        # Local fallback
        try:
            import ollama
            res = ollama.chat(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                options={"temperature": 0.3}
            )
            response = res["message"]["content"]
            return response, {"route": "local_fallback"}
        except Exception as fallback_error:
            return f"Sorry, I had an issue: {str(fallback_error)}", {"route": "error"}