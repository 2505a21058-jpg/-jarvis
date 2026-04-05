
import subprocess
import time
from dotenv import load_dotenv
load_dotenv()

import ollama
from rich.console import Console
from rich.panel import Panel

from voice import speak
from skills.router import route_query
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


def is_casual_greeting(query: str) -> bool:
    q = query.lower().strip()
    casual = ["hi", "hello", "hey", "sup", "yo", "ntg", "ntgggg", "gud for now", "nothing much"]
    return q in casual or any(q.startswith(g) for g in casual)


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

            # Mode Switching
            if lower in MODE_COMMANDS:
                new_mode = MODE_COMMANDS[lower]
                if new_mode != current_mode:
                    current_mode = new_mode
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
                msg = "Got it Sir, remembered."
                console.print(f"[bold green]JARVIS:[/bold green] {msg}")
                if tts_enabled:
                    speak(msg)
                continue

            # ✅ FIXED: allow router to use skills
            response, route = route_query(user_input, mode=current_mode)

            # Clean response
            if "JARVIS:" in response:
                response = response.split("JARVIS:")[-1].strip()
            if "User:" in response:
                response = response.split("User:")[-1].strip()

            # Save to memory
            add_to_conversation(user_input, response)
            add_experience(f"User: {user_input}")

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
