# skills/router.py
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime
import json
import os
import ollama
import random
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote_plus

from memory.core import get_context_for_mode, load_profile

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
GREETING_PATTERNS = {
    "hi", "hello", "hey", "yo",
    "hi jarvis", "hello jarvis", "hey jarvis", "yo jarvis",
}
BANG_ALIASES = {
    "youtube": "!yt",
    "yt": "!yt",
    "amazon": "!am",
    "spotify": "!sp",
    "music": "!sp",
    "songs": "!sp",
    "wikipedia": "!w",
    "wiki": "!w",
    "github": "!gh",
}
FAST_MODE_MODEL = "llama3.2:3b"
FAST_MODE_KEEP_ALIVE = "10m"
NERD_CLASSIFIER_MODEL = "llama3.2:3b"
AGENT_PLANNER_MODEL = "llama3.2:3b"
PLAY_MUSIC_PATTERN = re.compile(
    rf"^{COMMAND_PREFIX}(?:play(?:\s+some)?\s+music|play\s+songs|open\s+spotify|start\s+spotify)\b"
)
DEBUG = False
FAST_RECALL_DB_PATH = Path("memory") / "fast_recall.db"
FAST_RECALL_TABLE = "fast_recall"
MIN_RECALL_QUERY_LENGTH = 8
FAST_RECALL_SIMILARITY_THRESHOLD = 0.7
FAST_RECALL_MATCH_LIMIT = 24
FAST_RECALL_MAX_ROWS = 500
FAST_RECALL_MAX_RESPONSE_LENGTH = 1200
FAST_RECALL_DELETE_BATCH = 50
FAST_RECALL_MAX_WORDS = 6
RECALL_FILLER_WORDS = {
    "a", "an", "actually", "buddy", "hey", "hello", "hi", "jarvis", "just",
    "kindly", "like", "much", "ntg", "please", "really", "sir", "well", "yo"
}
ACTION_TRIGGER_WORDS = {
    "open", "launch", "start", "search", "find", "browse", "look up",
    "weather", "time", "date", "pnr", "train",
    "youtube", "google", "amazon", "spotify"
}
query_counts = {}
_last_action_cache = {"query": "", "plan": None}
MODE_LLM_CONFIGS = {
    "fast": {
        "ollama": {
            "model": FAST_MODE_MODEL,
            "temperature": 0.7,
            "num_predict": 320,
        },
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.7,
            "max_tokens": 320,
        },
    },
    "smart": {
        "ollama": {
            "model": "qwen3:8b",
            "temperature": 0.6,
            "num_predict": 1400,
        },
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.6,
            "max_tokens": 1400,
        },
    },
    "nerd": {
        "ollama": {
            "model": "qwen3:14b",
            "temperature": 0.3,
            "num_predict_simple": 1400,
            "num_predict": 2200,
            "num_predict_complex": 4500,
        },
        "groq": {
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.35,
            "max_tokens_simple": 1400,
            "max_tokens": 2200,
            "max_tokens_complex": 4500,
        },
    },
}
_fast_recall_conn = None


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower()).strip()


def _normalize_short_text(query: str) -> str:
    words = re.findall(r"[a-z]+", query.lower())
    return " ".join(words)


def _is_greeting_query(query: str) -> bool:
    normalized = _normalize_short_text(query)
    return normalized in GREETING_PATTERNS


def _get_profile_name() -> str:
    try:
        profile = load_profile()
    except Exception:
        return ""

    name = str(profile.get("name", "")).strip()
    if not name or name.lower() == "sir":
        return ""
    return name.title() if name.islower() else name


def _build_greeting_response() -> str:
    name = _get_profile_name()
    if name:
        options = [
            f"Hey {name}, what's up?",
            f"Hi {name}, how's it going?",
            f"Hey {name}, what's on your mind?",
        ]
    else:
        options = [
            "Hey, what's up?",
            "Hi, how's it going?",
            "Hey, what's on your mind?",
        ]
    return random.choice(options)


def _cache_action_plan(query: str, plan: dict | None):
    _last_action_cache["query"] = _normalize_query(query)
    _last_action_cache["plan"] = plan


def _get_cached_action_plan(query: str) -> dict | None:
    normalized_query = _normalize_query(query)
    if _last_action_cache["query"] == normalized_query:
        cached_plan = _last_action_cache.get("plan")
        if isinstance(cached_plan, dict):
            return cached_plan
    return None


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return None

    return data if isinstance(data, dict) else None


def _should_use_action_agent(query: str) -> bool:
    lowered = _normalize_query(query)
    if not lowered:
        return False

    if lowered.startswith(("open ", "launch ", "start ", "search ", "find ", "browse ", "look up ", "play ")):
        return True

    return any(trigger in lowered for trigger in ACTION_TRIGGER_WORDS)


def _normalize_bang_name(platform: str) -> str:
    return _normalize_query(platform)


def _resolve_bang(platform: str) -> tuple[str, str]:
    platform_key = _normalize_bang_name(platform)
    bang = BANG_ALIASES.get(platform_key, "")
    return bang, platform_key


def _tool_open_app(app_name: str):
    normalized_app = _normalize_query(app_name)
    if "spotify" in normalized_app or normalized_app in {"music", "songs"}:
        return _tool_search_bang("!sp", "")

    from .open_app import open_app
    return open_app(app_name)


def _tool_search_web(query: str):
    from .browser import browse
    return browse(query)


def _tool_search_bang(bang: str, query: str = ""):
    cleaned_bang = bang.strip()
    cleaned_query = query.strip()
    search_text = " ".join(part for part in [cleaned_bang, cleaned_query] if part).strip()
    if not search_text:
        return _tool_search_web(query)

    from .browser import browse
    return browse(f"https://duckduckgo.com/?q={quote_plus(search_text)}")


def _tool_search_platform(platform: str, query: str = ""):
    bang, platform_key = _resolve_bang(platform)
    if bang:
        return _tool_search_bang(bang, query)

    fallback_query = " ".join(part for part in [platform_key or platform.strip(), query.strip()] if part).strip()
    return _tool_search_web(fallback_query)


def _tool_play_music(source: str = "spotify"):
    target = source.strip() or "spotify"
    if target.lower() in {"music", "songs"}:
        target = ""
    return _tool_search_platform("spotify", target)


def _tool_get_weather(city: str):
    from .weather import get_weather
    return get_weather(city or "Hyderabad")


def _tool_get_datetime():
    from .datetime_skill import get_datetime
    return get_datetime()


def _tool_check_pnr(pnr: str):
    from .train import check_pnr
    return check_pnr(pnr)


def _tool_get_live_train(train_number: str):
    from .train import get_live_train
    return get_live_train(train_number)


def _plan_action(query: str) -> dict | None:
    prompt = f"""You are an action planner for JARVIS.
Available actions:
- open_app: open a local app like chrome, notepad, calculator, file explorer
- search_web: open a website or search the web
- search_bang: search using a DuckDuckGo bang
- play_music: play music or open a music app/site
- none: no action tool applies

Return ONLY valid JSON in this format:
{{"action":"...", "parameters":{{}}}}

Rules:
- Use "none" if the query is general conversation or normal chat.
- Put app name in "app_name" for open_app.
- Put search text in "query" for search_web.
- For search_bang use these mappings:
  - youtube -> !yt
  - amazon -> !am
  - spotify -> !sp
  - wikipedia -> !w
  - github -> !gh
- Put bang in "bang" and search text in "query" for search_bang.
- Put source or app name in "source" for play_music.
- Do not include explanation text.

User query: {query}
"""

    try:
        response = ollama.chat(
            model=AGENT_PLANNER_MODEL,
            messages=[
                {"role": "system", "content": "Convert user requests into one JSON action only."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1, "num_predict": 100},
        )
        content = response["message"]["content"].strip()
        return _extract_json_object(content)
    except Exception:
        return None


def _execute_action_plan(plan: dict):
    action = str(plan.get("action", "")).strip().lower()
    parameters = plan.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}

    if action == "open_app":
        app_name = str(parameters.get("app_name", "")).strip()
        if app_name:
            return _tool_open_app(app_name)
        return None

    if action == "search_web":
        search_query = str(parameters.get("query", "")).strip()
        if search_query:
            return _tool_search_web(search_query)
        return None

    if action == "search_bang":
        bang = str(parameters.get("bang", "")).strip()
        search_query = str(parameters.get("query", "")).strip()
        if bang:
            return _tool_search_bang(bang, search_query)
        return _tool_search_web(search_query)

    if action == "play_music":
        source = str(parameters.get("source", "")).strip()
        return _tool_play_music(source or "spotify")

    return None


def _normalize_recall_query(query: str) -> str:
    lowered = query.lower().strip()
    lowered = re.sub(r"^(?:can|could|would|will)\s+you\s+", "", lowered)
    lowered = re.sub(r"^(?:tell\s+me\s+about|tell\s+me|explain)\s+", "", lowered)
    words = [
        word for word in re.findall(r"[a-z0-9']+", lowered)
        if word not in RECALL_FILLER_WORDS
    ]
    return " ".join(words).strip()


def _should_run_fuzzy_recall(query_key: str) -> bool:
    return 0 < len(query_key.split()) <= FAST_RECALL_MAX_WORDS


def _short_recall_label(text: str, max_len: int = 60) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _current_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log_recall(message: str):
    if DEBUG:
        print(f"[Recall] {message}")


def _ensure_fast_recall_schema(conn):
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FAST_RECALL_TABLE} (
            query TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            usage_count INTEGER DEFAULT 1,
            last_used TIMESTAMP
        )
        """
    )
    existing_columns = {
        str(row[1]).lower()
        for row in conn.execute(f"PRAGMA table_info({FAST_RECALL_TABLE})").fetchall()
    }
    if "last_used" not in existing_columns:
        conn.execute(f"ALTER TABLE {FAST_RECALL_TABLE} ADD COLUMN last_used TIMESTAMP")
    conn.commit()


def _get_fast_recall_connection():
    global _fast_recall_conn
    if _fast_recall_conn is None:
        FAST_RECALL_DB_PATH.parent.mkdir(exist_ok=True)
        _fast_recall_conn = sqlite3.connect(FAST_RECALL_DB_PATH)
        _fast_recall_conn.row_factory = sqlite3.Row
        _ensure_fast_recall_schema(_fast_recall_conn)
    return _fast_recall_conn


def _touch_fast_recall_entry(query_key: str):
    conn = _get_fast_recall_connection()
    conn.execute(
        f"""
        UPDATE {FAST_RECALL_TABLE}
        SET usage_count = usage_count + 1,
            last_used = ?
        WHERE query = ?
        """,
        (_current_timestamp(), query_key),
    )
    conn.commit()


def _recall_similarity_score(query_key: str, candidate_key: str) -> float:
    if not query_key or not candidate_key:
        return 0.0

    if query_key == candidate_key:
        return 1.0

    query_words = set(query_key.split())
    candidate_words = set(candidate_key.split())
    if not query_words or not candidate_words:
        return 0.0

    overlap = len(query_words & candidate_words)
    if overlap == 0:
        return 0.0

    union = len(query_words | candidate_words)
    query_coverage = overlap / len(query_words)
    candidate_coverage = overlap / len(candidate_words)
    jaccard = overlap / union if union else 0.0
    score = max(jaccard, min(query_coverage, candidate_coverage))

    if query_key in candidate_key or candidate_key in query_key:
        score = max(score, 0.85)

    return score


def _increment_query_count(query: str) -> str:
    query_key = _normalize_recall_query(query)
    if query_key:
        query_counts[query_key] = query_counts.get(query_key, 0) + 1
    return query_key


def _is_meaningful_recall_response(response: str) -> bool:
    if not response:
        return False

    response_text = response.strip()
    if len(response_text) < 12:
        return False
    if len(response_text) > FAST_RECALL_MAX_RESPONSE_LENGTH:
        return False

    lowered = response_text.lower()
    failure_prefixes = (
        "sorry sir, i ran into an issue:",
        "skill error:",
        "please provide",
        "i dont know how to open",
        "i don't know how to open",
    )
    if lowered.startswith(failure_prefixes):
        return False

    return bool(re.search(r"[a-z0-9]", lowered))


def _cleanup_fast_recall_table():
    conn = _get_fast_recall_connection()
    row_count = conn.execute(
        f"SELECT COUNT(*) FROM {FAST_RECALL_TABLE}"
    ).fetchone()[0]

    if row_count <= FAST_RECALL_MAX_ROWS:
        return

    delete_count = min(row_count - FAST_RECALL_MAX_ROWS, FAST_RECALL_DELETE_BATCH)
    conn.execute(
        f"""
        DELETE FROM {FAST_RECALL_TABLE}
        WHERE query IN (
            SELECT query
            FROM {FAST_RECALL_TABLE}
            ORDER BY usage_count ASC, last_used ASC
            LIMIT ?
        )
        """,
        (delete_count,),
    )
    conn.commit()
    _log_recall(f"cleanup removed {delete_count} old entries")


def get_quick_response(query: str) -> str | None:
    query_key = _normalize_recall_query(query)
    if len(query_key) < MIN_RECALL_QUERY_LENGTH:
        return None

    allow_fuzzy = _should_run_fuzzy_recall(query_key)

    conn = _get_fast_recall_connection()
    exact_row = conn.execute(
        f"""
        SELECT query, response
        FROM {FAST_RECALL_TABLE}
        WHERE query = ?
        """,
        (query_key,),
    ).fetchone()
    if exact_row:
        _touch_fast_recall_entry(query_key)
        _log_recall(f"exact hit: {_short_recall_label(query_key)}")
        return str(exact_row["response"]).strip()

    if not allow_fuzzy:
        _log_recall(f"skip fuzzy: long query ({_short_recall_label(query_key)})")
        return None

    like_query = f"%{query_key}%"
    candidate_rows = conn.execute(
        f"""
        SELECT query, response
        FROM {FAST_RECALL_TABLE}
        WHERE query LIKE ?
           OR ? LIKE '%' || query || '%'
        ORDER BY usage_count DESC, last_used DESC
        LIMIT ?
        """,
        (like_query, query_key, FAST_RECALL_MATCH_LIMIT),
    ).fetchall()

    best_row = None
    best_score = 0.0
    for row in candidate_rows:
        candidate_query = str(row["query"]).strip()
        score = _recall_similarity_score(query_key, candidate_query)
        if score > best_score:
            best_score = score
            best_row = row

    if best_row and best_score >= FAST_RECALL_SIMILARITY_THRESHOLD:
        matched_query = str(best_row["query"]).strip()
        _touch_fast_recall_entry(matched_query)
        _log_recall(
            f"similar hit: {_short_recall_label(query_key)} -> "
            f"{_short_recall_label(matched_query)} ({best_score:.2f})"
        )
        return str(best_row["response"]).strip()

    _log_recall(f"miss: {_short_recall_label(query_key)}")

    return None


def maybe_store_response(query: str, response: str, mode: str):
    query_key = _normalize_recall_query(query)
    response_text = response.strip()

    if mode not in {"smart", "nerd"}:
        return
    if _is_greeting_query(query):
        _log_recall("skip store: greeting")
        return
    if len(query_key) < MIN_RECALL_QUERY_LENGTH:
        _log_recall(f"skip store: query too short ({_short_recall_label(query_key)})")
        return
    if query_counts.get(query_key, 0) < 2:
        _log_recall(f"skip store: not repeated yet ({_short_recall_label(query_key)})")
        return
    if not _is_meaningful_recall_response(response_text):
        _log_recall(f"skip store: response not suitable ({_short_recall_label(query_key)})")
        return

    timestamp = _current_timestamp()
    conn = _get_fast_recall_connection()
    existing = conn.execute(
        f"SELECT usage_count FROM {FAST_RECALL_TABLE} WHERE query = ?",
        (query_key,),
    ).fetchone()

    if existing:
        conn.execute(
            f"""
            UPDATE {FAST_RECALL_TABLE}
            SET response = ?,
                usage_count = usage_count + 1,
                last_used = ?
            WHERE query = ?
            """,
            (response_text, timestamp, query_key),
        )
        _log_recall(f"updated: {_short_recall_label(query_key)}")
    else:
        conn.execute(
            f"""
            INSERT INTO {FAST_RECALL_TABLE} (query, response, usage_count, last_used)
            VALUES (?, ?, 1, ?)
            """,
            (query_key, response_text, timestamp),
        )
        _log_recall(f"stored: {_short_recall_label(query_key)}")
    conn.commit()
    _cleanup_fast_recall_table()


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


def _extract_open_target(query: str) -> str:
    match = OPEN_PATTERN.match(_normalize_query(query))
    if not match:
        return ""
    return _clean_target(match.group("target"))


def is_simple_app_command(query: str) -> bool:
    q = _normalize_query(query)
    if not q.startswith("open "):
        return False

    if " and " in q or " search " in q:
        return False

    target = _extract_open_target(query)
    if not target:
        return False

    if not _is_short_target(target):
        return False

    return _looks_like_local_app(target) or _looks_like_web_target(target)


def handle_skill(query: str):
    q = _normalize_query(query)
    try:
        open_match = OPEN_PATTERN.match(q)
        if open_match:
            target = _clean_target(open_match.group("target"))
            if _is_short_target(target) and _looks_like_local_app(target):
                return _tool_open_app(target)
            if _is_short_target(target) and _looks_like_web_target(target):
                return _tool_search_web(f"open {target}")

        if PLAY_MUSIC_PATTERN.match(q):
            return _tool_play_music("spotify")

        search_match = SEARCH_PATTERN.match(q)
        if search_match:
            target = _clean_target(search_match.group("target"))
            if target:
                return _tool_search_web(query)

        if (PNR_PATTERN.match(q) or TRAIN_PATTERN.match(q)) and len(q) <= 140:
            pnr_match = re.search(r"\d{10}", q)
            if pnr_match:
                return _tool_check_pnr(pnr_match.group())
            train_match = re.search(r"\d{5}", q)
            if train_match:
                return _tool_get_live_train(train_match.group())
            return "Please provide a valid PNR or train number Sir."

        if WEATHER_PATTERN.match(q) and len(q) <= 120:
            city = _extract_weather_city(q)
            return _tool_get_weather(city)

        if TIME_PATTERN.match(q) and len(q) <= 80:
            return _tool_get_datetime()

    except Exception as e:
        return f"Skill error: {str(e)}"

    return None


def is_simple_command(query: str) -> bool:
    q = _normalize_query(query)
    if not q:
        return False

    if PLAY_MUSIC_PATTERN.match(q):
        return True
    if OPEN_PATTERN.match(q):
        return is_simple_app_command(query)
    if SEARCH_PATTERN.match(q):
        return False
    if WEATHER_PATTERN.match(q):
        return len(q.split()) <= 10
    if TIME_PATTERN.match(q):
        return True
    if PNR_PATTERN.match(q) or TRAIN_PATTERN.match(q):
        return True

    return False


def is_complex_command(query: str) -> bool:
    q = _normalize_query(query)
    if not q:
        return False

    if SEARCH_PATTERN.match(q):
        return True

    if OPEN_PATTERN.match(q) and (" and " in q or " search " in q):
        return True

    if " and " in q and _should_use_action_agent(query):
        return True

    return _should_use_action_agent(query) and not is_simple_command(query)


def get_mode_system_prompt(mode: str) -> str:
    base_prompt = (
        "You are Jarvis, a personal AI assistant created by the user.\n\n"
        "Thinking:\n"
        "- Stay calm, objective, and emotionally detached.\n"
        "- Focus on outcomes, tradeoffs, and practical reasoning.\n"
        "- Identify key risks, assumptions, and opportunities.\n"
        "- Point out flawed thinking clearly.\n"
        "- Be realistic and results-oriented.\n"
        "- Do not suggest harmful, illegal, or unethical actions.\n\n"
        "Style:\n"
        "- Start with a direct answer.\n"
        "- Add clear reasoning.\n"
        "- Optionally include a sharp insight if it adds value.\n"
        "- Keep responses concise and natural.\n"
        "- Avoid unnecessary structure in simple queries.\n"
        "- Do not roleplay or use fictional identity.\n"
        "- Do not use dramatic or emotional language.\n"
        "- Do not use sir or master language.\n"
        "- Avoid long essays unless necessary.\n"
        "- Avoid repeating obvious points."
    )

    if mode == "fast":
        return base_prompt + "\n\nFAST mode: give a short answer with optional insight. Keep it within 3 to 4 lines."
    if mode == "smart":
        return base_prompt + "\n\nSMART mode: give the answer, the reasoning, and the key tradeoffs."
    if mode == "nerd":
        return base_prompt + "\n\nNERD mode: use a structured breakdown of situation, risks, opportunities, and strategy."
    return base_prompt

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


def _get_mode_llm_config(mode: str) -> dict:
    return MODE_LLM_CONFIGS.get(mode, MODE_LLM_CONFIGS["smart"])


def _classify_nerd_query(query: str) -> str:
    cleaned_query = query.strip()
    if not cleaned_query:
        return "medium"

    classification_prompt = (
        "Classify this query into:\n"
        "- simple (definition/basic info)\n"
        "- medium (explanation/learning)\n"
        "- complex (coding, building, analysis)\n\n"
        f"Query: {cleaned_query}\n\n"
        "Answer only one word: simple / medium / complex"
    )

    try:
        res = ollama.chat(
            model=NERD_CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": "Classify user queries with a one-word answer only."},
                {"role": "user", "content": classification_prompt}
            ],
            options={
                "temperature": 0,
                "num_predict": 8,
            }
        )
        content = res["message"]["content"].strip().lower()
        match = re.search(r"\b(simple|medium|complex)\b", content)
        if match:
            return match.group(1)
    except Exception:
        pass

    return "medium"


def _resolve_mode_llm_config(mode: str, nerd_level: str | None = None) -> tuple[dict, dict]:
    mode_config = _get_mode_llm_config(mode)
    ollama_config = dict(mode_config["ollama"])
    groq_config = dict(mode_config["groq"])

    if mode == "nerd":
        if nerd_level == "simple":
            ollama_config["num_predict"] = ollama_config.get("num_predict_simple", ollama_config["num_predict"])
            groq_config["max_tokens"] = groq_config.get("max_tokens_simple", groq_config["max_tokens"])
        elif nerd_level == "complex":
            ollama_config["num_predict"] = ollama_config.get("num_predict_complex", ollama_config["num_predict"])
            groq_config["max_tokens"] = groq_config.get("max_tokens_complex", groq_config["max_tokens"])
        ollama_config.pop("num_predict_simple", None)
        ollama_config.pop("num_predict_complex", None)
        groq_config.pop("max_tokens_simple", None)
        groq_config.pop("max_tokens_complex", None)

    return ollama_config, groq_config


def _build_nerd_response_guidance(level: str) -> str:
    common_lines = [
        "Start with a direct answer.",
        "Then explain the reasoning.",
        "Organize the response around situation, risks, opportunities, and strategy when helpful.",
        "Add a sharp insight only when it truly adds value.",
        "Be detailed but concise.",
        "Avoid unnecessary expansion.",
        "Avoid repeating obvious points.",
        "Do not use dramatic or emotional language.",
        "Finish responses cleanly.",
    ]

    if level == "simple":
        common_lines.append("Keep the response light, clear, and analytical without overthinking.")
    elif level == "medium":
        common_lines.append("Use structure only where it improves clarity.")
        common_lines.append("Focus on practical tradeoffs and realistic implications.")
    else:
        common_lines.extend([
            "Think step by step internally before writing the final answer.",
            "Go deeper on reasoning, tradeoffs, and consequences.",
            "Take a clear stance when the question invites judgment.",
            "Explain strengths, weaknesses, risks, and opportunities when relevant.",
            "Do not expose raw chain-of-thought.",
        ])

    return "\n".join(common_lines)


def _run_groq_chat(config: dict, system_prompt: str, full_prompt: str):
    completion = groq_client.chat.completions.create(
        model=config["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"]
    )
    response = completion.choices[0].message.content.strip()
    return response, {"route": "groq"}


def _run_ollama_chat(config: dict, system_prompt: str, full_prompt: str):
    res = ollama.chat(
        model=config["model"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ],
        options={
            "temperature": config["temperature"],
            "num_predict": config["num_predict"],
        }
    )
    response = res["message"]["content"].strip()
    return response, {"route": "local"}


def _run_fast_mode_llm(query: str):
    system_prompt = get_mode_system_prompt("fast")
    cleaned_query = query.strip()

    if DEBUG:
        print("[FAST] Provider: OLLAMA")
        print(f"[FAST] Model: {FAST_MODE_MODEL}")
    print("JARVIS: ", end="", flush=True)

    response_parts = []
    stream = ollama.chat(
        model=FAST_MODE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": cleaned_query}
        ],
        stream=True,
        keep_alive=FAST_MODE_KEEP_ALIVE,
        options={
            "temperature": 0.7,
            "num_predict": 180,
        }
    )

    try:
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if not token:
                continue
            response_parts.append(token)
            print(token, end="", flush=True)
    finally:
        print()

    response = "".join(response_parts).strip()
    return response, {"route": "fast_ollama", "streamed": True}


def _build_response_guidance(mode: str, query: str) -> tuple[str, str | None]:
    nerd_level = None
    response_guidance = (
        "Start with a direct answer.\n"
        "Then add clear reasoning.\n"
        "Optionally add a sharp insight if it helps.\n"
        "Be concise but meaningful.\n"
        "Avoid dramatic or emotional language.\n"
        "Avoid long essays unless necessary.\n"
        "Avoid repeating obvious points."
    )

    if mode == "fast":
        response_guidance = (
            "Start with a direct answer.\n"
            "Then explain why briefly.\n"
            "Add one sharp insight only if it genuinely helps.\n"
            "Be concise, sharp, and meaningful.\n"
            "Keep it within 3 to 4 lines.\n"
            "Do not overthink simple queries.\n"
            "Avoid repeating obvious points."
        )
    elif mode == "smart":
        response_guidance = (
            "Start with a direct answer.\n"
            "Then explain the reasoning.\n"
            "Then include the key tradeoffs.\n"
            "Add a sharp insight when useful.\n"
            "Be balanced, practical, and concise.\n"
            "Avoid generic or overly safe wording.\n"
            "Avoid repeating obvious points."
        )
    elif mode == "nerd":
        nerd_level = _classify_nerd_query(query)
        response_guidance = _build_nerd_response_guidance(nerd_level)

    return response_guidance, nerd_level


def _run_mode_llm(query: str, mode: str):
    context = get_context_for_mode(mode, query)
    system_prompt = get_mode_system_prompt(mode)
    response_guidance, nerd_level = _build_response_guidance(mode, query)

    full_prompt = f"""{system_prompt}

Context:
{context}

User: {query}

{response_guidance}"""

    ollama_config, groq_config = _resolve_mode_llm_config(mode, nerd_level)

    try:
        return _run_ollama_chat(ollama_config, system_prompt, full_prompt)
    except Exception:
        return _run_groq_chat(groq_config, system_prompt, full_prompt)


def route_query(query: str, mode: str = "smart", force_llm: bool = False):
    simple_app_command = is_simple_app_command(query)
    simple_command = is_simple_command(query)
    complex_command = is_complex_command(query)

    # 1. Skill fast path
    if not force_llm and simple_app_command:
        skill_response = handle_skill(query)
        if skill_response:
            print("[FLOW] SKILL")
            return skill_response, {"route": "skill"}

    if not force_llm and simple_command and not complex_command:
        skill_response = handle_skill(query)
        if skill_response:
            print("[FLOW] SKILL")
            return skill_response, {"route": "skill"}

    # 2. Agent planner for complex commands
    if not force_llm and complex_command:
        cached_plan = _get_cached_action_plan(query)
        if cached_plan:
            cached_response = _execute_action_plan(cached_plan)
            if cached_response:
                print("[FLOW] AGENT")
                return cached_response, {"route": "agent_cached"}

        action_plan = _plan_action(query)
        if action_plan:
            planned_response = _execute_action_plan(action_plan)
            if planned_response:
                _cache_action_plan(query, action_plan)
                print("[FLOW] AGENT")
                return planned_response, {"route": "agent"}

    # 3. FAST mode fallback for normal chat
    if mode == "fast":
        if DEBUG:
            print("[FLOW] FAST")
        try:
            return _run_fast_mode_llm(query)
        except Exception as e:
            return f"Sorry Sir, I ran into an issue: {str(e)}", {"route": "error"}

    if _is_greeting_query(query):
        return _build_greeting_response(), {"route": "greeting"}

    # 4. Recall (optional, gated)
    if not force_llm:
        _increment_query_count(query)
        recall_response = get_quick_response(query)
        if recall_response:
            return recall_response, {"route": "quick_recall"}

    # 5. Memory + LLM
    try:
        response, meta = _run_mode_llm(query, mode)
        maybe_store_response(query, response, mode)
        return response, meta
    except Exception as e:
        return f"Sorry Sir, I ran into an issue: {str(e)}", {"route": "error"}
