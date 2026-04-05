# skills/router.py
from groq import Groq
from dotenv import load_dotenv
import os
import ollama
import re

from memory.core import get_context_for_mode

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))



COMMAND_PREFIX = r"(?:jarvis[\s,:-]+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?"
OPEN_PATTERN = re.compile(rf"^{COMMAND_PREFIX}(?:open|launch|start)\s+(?P<target>.+)$")
SEARCH_PATTERN = re.compile(
    rf"^{COMMAND_PREFIX}(?:web\s+search|google\s+search|duckduckgo|search(?:\s+for)?|look\s+up|find\s+on|browse\s+for)\s+(?P<target>.+)$"
)
PNR_PATTERN = re.compile(rf"^{COMMAND_PREFIX}(?:check\s+)?pnr\b")
TRAIN_PATTERN = re.compile(rf"(?:^{COMMAND_PREFIX}(?:check\s+)?train\s+status\b|^{COMMAND_PREFIX}live\s+train\b)")
WEATHER_PATTERN = re.compile(
    rf"^{COMMAND_PREFIX}(?:weather\b|what(?:'s| is)\s+the\s+weather(?:\s+like)?\b|tell\s+me\s+the\s+weather\b|show\s+me\s+the\s+weather\b)"
)
TIME_PATTERN = re.compile(
    rf"^{COMMAND_PREFIX}(?:time\b|date\b|current\s+time\b|current\s+date\b|what(?:'s| is)\s+the\s+time\b|what(?:'s| is)\s+the\s+date\b|today(?:'s)?\s+date\b)"
)

LOCAL_APP_HINTS = ("chrome", "browser", "google", "notepad", "note", "calculator", "calc", "files", "explorer", "folder")
WEB_TARGET_HINTS = (
    "youtube", "amazon", "github", "maps", "google maps", "reddit",
    "wikipedia", "wiki", "stackoverflow", "stack overflow", "twitter",
    "instagram", "flipkart", "netflix", "spotify", "translate", "news",
    "images", "google", "irctc"
)


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower()).strip()


def _clean_target(target: str) -> str:
    cleaned = target.strip().strip(" .?!")
    cleaned = re.sub(r"\b(?:for me|please)$", "", cleaned).strip(" ,.")
    return cleaned


def _is_short_target(target: str, max_words: int = 6, max_chars: int = 60) -> bool:
    words = re.findall(r"\w+", target)
    return len(words) <= max_words and len(target) <= max_chars


def _looks_like_local_app(target: str) -> bool:
    return any(hint in target for hint in LOCAL_APP_HINTS)


def _looks_like_web_target(target: str) -> bool:
    domain_like = re.search(r"(?:[a-z0-9-]+\.)+[a-z]{2,}", target)
    return bool(domain_like) or any(hint in target for hint in WEB_TARGET_HINTS)


def _extract_weather_city(query: str) -> str:
    city = re.sub(
        rf"^{COMMAND_PREFIX}(?:weather\b|what(?:'s| is)\s+the\s+weather(?:\s+like)?\b|tell\s+me\s+the\s+weather\b|show\s+me\s+the\s+weather\b)",
        "",
        query,
    ).strip()
    city = re.sub(r"^(?:in|for)\s+", "", city).strip()
    city = re.sub(r"\b(?:today|now|right now|currently)\b", "", city).strip(" ,.")
    return city or "Hyderabad"


def handle_skill(query: str):
    q = _normalize_query(query)
    try:
        open_match = OPEN_PATTERN.match(q)
        if open_match:
            target = _clean_target(open_match.group("target"))
            if _is_short_target(target) and _looks_like_local_app(target):
                from .open_app import open_app
                return open_app(target)
            if _is_short_target(target) and _looks_like_web_target(target):
                from .browser import browse
                return browse(f"open {target}")

        search_match = SEARCH_PATTERN.match(q)
        if search_match:
            target = _clean_target(search_match.group("target"))
            if target:
                from .browser import browse
                return browse(query)

        if (PNR_PATTERN.match(q) or TRAIN_PATTERN.match(q)) and len(q) <= 140:
            from .train import check_pnr, get_live_train
            pnr_match = re.search(r"\d{10}", q)
            if pnr_match:
                return check_pnr(pnr_match.group())
            train_match = re.search(r"\d{5}", q)
            if train_match:
                return get_live_train(train_match.group())
            return "Please provide a valid PNR or train number Sir."

        if WEATHER_PATTERN.match(q) and len(q) <= 120:
            from .weather import get_weather
            city = _extract_weather_city(q)
            return get_weather(city)

        if TIME_PATTERN.match(q) and len(q) <= 80:
            from .datetime_skill import get_datetime
            return get_datetime()

    except Exception as e:
        return f"Skill error: {str(e)}"

    return None


def get_mode_system_prompt(mode: str) -> str:
    if mode == "fast":
        return """You are JARVIS — casual, sharp, and fast.
Reply naturally like a smart friend. Keep responses short and friendly.
You can try to open apps if the skill is available.
If you cannot do something, just say so honestly without long explanations."""

    elif mode == "smart":
        return """You are JARVIS — helpful, clear, and intelligent.
Give balanced answers.
You can try to open apps if the skill is available."""

    elif mode == "nerd":
        return """You are JARVIS — deep thinking and thorough.
Think step-by-step.
You can try to open apps if the skill is available."""

    return "You are JARVIS — helpful and intelligent assistant."


def route_query(query: str, mode: str = "smart", force_llm: bool = False):
    # Try skills first (this is important for "open" commands)
    if not force_llm:
        skill_response = handle_skill(query)
        if skill_response:
            return skill_response, {"route": "skill"}

    # If no skill matched, use LLM
    context = get_context_for_mode(mode, query)
    system_prompt = get_mode_system_prompt(mode)

    full_prompt = f"""{system_prompt}

Context:
{context}

User: {query}

Answer directly and naturally."""

    max_tokens_map = {"fast": 600, "smart": 1200, "nerd": 4000}
    max_tokens = max_tokens_map.get(mode, 1200)

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt}
            ],
            temperature=0.5,
            max_tokens=max_tokens
        )
        response = completion.choices[0].message.content.strip()
        return response, {"route": "groq"}

    except Exception:
        try:
            model_to_use = {"fast": "qwen3:8b", "smart": "qwen3:8b", "nerd": "qwen3:14b"}.get(mode, "qwen3:8b")
            res = ollama.chat(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt}
                ],
                options={"temperature": 0.5}
            )
            response = res["message"]["content"].strip()
            return response, {"route": "local"}
        except Exception as e:
            return f"Sorry Sir, I ran into an issue: {str(e)}", {"route": "error"}
