
import subprocess
import time
import re
from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel

from model_manager import model_manager
from voice import speak
from skills.router import route_query, conversation_history
from skills.browser import close_browser
from memory.core import (
    load_profile,
    add_fact,
    add_experience,
    add_to_conversation,
    summarize_and_store_long_term_memory
)

console = Console()
tts_enabled = False
current_mode = "fast"
DEBUG = True

CASUAL_GREETINGS = {
    "hi", "hello", "hey", "sup", "yo", "what's up", "whats up",
    "nothing much", "gud for now", "ntg", "ntgggg"
}
ACTION_WORDS = {
    "open", "search", "play", "browse", "find", "launch", "start",
    "weather", "time", "date", "pnr", "train", "remember", "check"
}
FACT_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
    "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
    "or", "so", "that", "the", "this", "to", "was", "what", "when",
    "where", "who", "why", "with", "you", "your", "about", "know"
}

# ==================== 3 MODES CONFIG (Minimal) ====================
MODELS = {
    "fast":  "llama3.2:3b",
    "smart": "qwen3:8b",
    "nerd":  "qwen3:14b"
}

MODE_COMMANDS = {
    "fast mode": "fast",
    "normal mode": "fast",
    "smart mode": "smart",
    "nerd mode": "nerd",
    "deep mode": "nerd",
    "claude mode": "nerd"
}


def start_ollama():
    try:
        console.print("[dim]Warming up local model...[/dim]")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
    except Exception as e:
        console.print(f"[bold red]Failed to start Ollama: {e}[/bold red]")


def warmup_startup_models():
    try:
        model_manager.warm_model("fast", force=True)
    except Exception as e:
        console.print(f"[dim]Model warmup warning: {e}[/dim]")


def _debug_log(message: str):
    if DEBUG:
        console.print(f"[dim][Debug][/dim] {message}")


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s']+", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_keywords(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {word for word in words if len(word) >= 3 and word not in FACT_STOPWORDS}


def is_casual_greeting(query: str) -> bool:
    normalized = _normalize_text(query)
    if not normalized:
        return False

    words = normalized.split()
    if len(words) > 3:
        return False

    if any(word in ACTION_WORDS for word in words):
        return False

    return normalized in CASUAL_GREETINGS


def _is_action_like_query(query: str) -> bool:
    normalized = _normalize_text(query)
    return any(word in ACTION_WORDS for word in normalized.split())


def _is_self_profile_query(query: str) -> bool:
    lowered = _normalize_text(query)
    return (
        "about me" in lowered
        or "know about me" in lowered
        or "who am i" in lowered
        or "what do you know about me" in lowered
        or lowered in {"me", "my profile"}
    )


def _format_fact_entry(key: str, value: str) -> str:
    clean_key = str(key).strip()
    clean_value = str(value).strip()
    if not clean_key or clean_key.lower() == clean_value.lower():
        return clean_value
    return f"{clean_key}: {clean_value}"


def _get_relevant_profile_facts(query: str, profile: dict, limit: int = 4) -> list[str]:
    facts = profile.get("facts", {})
    if not isinstance(facts, dict) or not facts:
        return []

    if _is_self_profile_query(query):
        scored_facts = []
        for key, value in facts.items():
            fact_text = _format_fact_entry(key, value)
            if not fact_text:
                continue
            richness = len(_extract_keywords(fact_text))
            scored_facts.append((richness, -len(fact_text), fact_text))

        scored_facts.sort(reverse=True)
        return [fact_text for _, _, fact_text in scored_facts[:limit]]

    query_keywords = _extract_keywords(query)
    if not query_keywords:
        return []

    scored_facts = []
    for key, value in facts.items():
        fact_text = _format_fact_entry(key, value)
        fact_keywords = _extract_keywords(fact_text)
        overlap = query_keywords & fact_keywords
        if not overlap:
            continue

        score = len(overlap) * 3
        if key and (_extract_keywords(str(key)) & query_keywords):
            score += 2
        scored_facts.append((score, len(fact_keywords), -len(fact_text), fact_text))

    if not scored_facts:
        return []

    scored_facts.sort(reverse=True)
    return [fact_text for _, _, _, fact_text in scored_facts[:limit]]


def _build_relevant_memory_context(query: str, profile: dict) -> tuple[str, int]:
    if is_casual_greeting(query) or _is_action_like_query(query):
        return "", 0

    relevant_facts = _get_relevant_profile_facts(query, profile, limit=4)
    if not relevant_facts:
        return "", 0

    lines = ["Relevant user facts:"]
    lines.extend(f"- {fact}" for fact in relevant_facts)
    return "\n".join(lines), len(relevant_facts)


def _restore_router_user_message(original_query: str, routed_query: str):
    if original_query == routed_query:
        return

    for message in reversed(conversation_history):
        if message.get("role") == "user" and message.get("content") == routed_query:
            message["content"] = original_query
            return


def shutdown_jarvis():
    try:
        summarize_and_store_long_term_memory()
    except Exception as e:
        console.print(f"[dim]Memory summary warning: {e}[/dim]")

    try:
        close_browser()
    except Exception as e:
        console.print(f"[dim]Browser shutdown warning: {e}[/dim]")


def run_jarvis():
    global tts_enabled, current_mode
    start_ollama()
    warmup_startup_models()

    profile = load_profile()
    name = profile.get("name", "Sir")

    console.print(Panel("JARVIS Online", style="bold green"))
    console.print(f"[bold green]Welcome back, {name}.[/bold green]\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            lower = user_input.lower().strip()
            _debug_log(f"Input: {user_input}")

            # Mode Switching
            if lower in MODE_COMMANDS:
                new_mode = MODE_COMMANDS[lower]
                if new_mode != current_mode:
                    current_mode = new_mode
                    model_manager.preload_mode_model(current_mode)
                    console.print(f"[bold cyan]→ Switched to {current_mode.upper()} MODE[/bold cyan]")
                continue

            # Voice controls
            if lower in ["speak on", "tts on", "voice on"]:
                tts_enabled = True
                console.print("[bold cyan]Voice enabled[/bold cyan]")
                continue
            if lower in ["speak off", "tts off", "voice off", "shut up"]:
                tts_enabled = False
                console.print("[bold cyan]Voice disabled[/bold cyan]")
                continue

            if lower in ["quit", "exit", "bye"]:
                if tts_enabled:
                    speak("Later Sir.")
                console.print("[bold red]Later, Sir.[/bold red]")
                shutdown_jarvis()
                break

            # Remember command
            if lower.startswith("remember "):
                fact = user_input[9:].strip()
                add_fact(fact[:60], fact)
                add_experience(f"User told me: {fact}")
                profile = load_profile()
                msg = "Got it Sir, remembered."
                console.print(f"[bold green]JARVIS:[/bold green] {msg}")
                if tts_enabled:
                    speak(msg)
                continue

            # ✅ FIXED: allow router to use skills
            memory_context, injected_facts = _build_relevant_memory_context(user_input, profile)
            routed_input = user_input
            if memory_context:
                routed_input = f"{memory_context}\n\nUser query: {user_input}"
            _debug_log(f"Facts injected: {injected_facts}")

            response, route = route_query(routed_input, mode=current_mode)
            _restore_router_user_message(user_input, routed_input)
            _debug_log(
                f"Skill used: {'yes' if route.get('route') == 'skill' else 'no'} "
                f"(route={route.get('route', 'unknown')})"
            )

            # Clean response
            if "JARVIS:" in response:
                response = response.split("JARVIS:")[-1].strip()
            if "User:" in response:
                response = response.split("User:")[-1].strip()

            # Save to memory
            add_to_conversation(user_input, response)
            add_experience(f"User: {user_input}")

            if not route.get("streamed"):
                console.print(f"[bold green]JARVIS:[/bold green] {response}")
            if tts_enabled:
                speak(response)

        except KeyboardInterrupt:
            console.print("\n[bold red]Later, Sir.[/bold red]")
            shutdown_jarvis()
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")

    shutdown_jarvis()


if __name__ == "__main__":
    run_jarvis()
