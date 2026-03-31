from groq import Groq
from dotenv import load_dotenv
import os
import ollama

from memory.core import search_experiences

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

print("✅ Final Hybrid Router Loaded")


def handle_skill(query: str):
    """Route query to explicit skills if matched."""
    q = query.lower().strip()

    try:
        # Web Search / Browser
        if any(phrase in q for phrase in ["web search", "search for", "look up", "find on", "duckduckgo", "google search", "browse for", "search about"]):
            from .browser import browse
            return browse(query)

        # Open Apps
        if any(w in q for w in ["open ", "launch ", "start "]):
            from .open_app import open_app
            return open_app(query)

        # Train / PNR
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

    except Exception as e:
        return f"Skill error: {str(e)}"

    return None


JARVIS_SYSTEM_PROMPT = """You are JARVIS — a sharp, witty AI assistant who talks like a chill, smart friend.

Personality:
- Casual and direct. Short sentences. No fluff.
- Light humor when it fits naturally — never forced.
- Use "Sir" occasionally, not in every single reply.
- NEVER open with filler like "Certainly!" or "Of course!".
- Never lecture. Be concise.

Response length:
- Greetings → 1-2 sentences.
- Explanations → 3-5 sentences.
- Technical help → as long as needed, no padding.

Memory rules:
- ONLY mention stored facts if directly relevant.
- Greetings → respond warmly, nothing else.
- Do NOT volunteer irrelevant facts."""


def process_query(full_prompt: str):
    """LLM call with Groq → Ollama fallback."""
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.45,
            max_tokens=600
        )
        response = completion.choices[0].message.content.strip()
        return response, {"route": "groq"}
    except Exception:
        try:
            res = ollama.chat(
                model="llama3.2",
                messages=[
                    {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                    {"role": "user", "content": full_prompt}
                ],
                options={"temperature": 0.45}
            )
            response = res["message"]["content"].strip()
            return response, {"route": "local_fallback"}
        except Exception as fallback_error:
            return f"Sorry, ran into an issue: {str(fallback_error)}", {"route": "error"}


def route_query(query: str, context: str = "", force_llm: bool = False):
    """
    Unified dispatcher:
    1. Skills
    2. Structured experiences.json (memory)
    3. LLM fallback
    """
    if not force_llm:
        # 1. Skills
        skill_response = handle_skill(query)
        if skill_response:
            return skill_response, {"route": "skill"}

        # 2. Memory (structured experiences first)
        memory_response = search_experiences(query)
        if memory_response:
            return memory_response, {"route": "memory"}

    # 3. LLM fallback
    prompt = f"""{context}
User: {query}

You are JARVIS - helpful, natural, and intelligent assistant.
Answer based on the conversation flow above if relevant.
Otherwise answer normally. Be concise and practical."""
    return process_query(prompt)
