import subprocess
import time
from dotenv import load_dotenv
load_dotenv()

import ollama
from voice import speak
from skills.router import route_query
from rich.console import Console
from rich.panel import Panel

from memory.core import (
    load_profile,
    add_fact,
    add_experience,
    add_to_conversation,
    get_conversation_context
)

console = Console()
tts_enabled = False


def start_ollama():
    """Start Ollama server locally if not already running."""
    try:
        console.print("[dim]Warming up local model...[/dim]")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(3)
    except Exception as e:
        console.print(f"[bold red]Failed to start Ollama:[/bold red] {e}")


def is_casual_greeting(query: str) -> bool:
    """Detect casual greetings for short replies."""
    q = query.lower().strip()
    casual = [
        "hi", "hello", "hey", "all gud", "how are you",
        "sup", "yo", "ntg much", "gud for now"
    ]
    return q in casual or any(q.startswith(g) for g in casual)


def run_jarvis():
    """Main runtime loop for JARVIS."""
    global tts_enabled
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

            # Voice controls
            if lower in ["speak on", "tts on", "voice on"]:
                tts_enabled = True
                console.print("[bold cyan]Voice enabled[/bold cyan]")
                continue
            if lower in ["speak off", "tts off", "voice off", "shut up"]:
                tts_enabled = False
                console.print("[bold cyan]Voice disabled[/bold cyan]")
                continue

            # Exit
            if lower in ["quit", "exit", "bye"]:
                if tts_enabled:
                    speak("Later Sir.")
                console.print("[bold red]Later, Sir.[/bold red]")
                break

            # Memory add
            if lower.startswith("remember "):
                fact = user_input[9:].strip()
                add_fact(fact[:60], fact)
                add_experience(f"User told me: {fact}")
                msg = "Got it Sir, remembered."
                console.print(f"[bold green]JARVIS:[/bold green] {msg}")
                if tts_enabled:
                    speak(msg)
                continue

            context = get_conversation_context()

            # Greeting shortcut
            if is_casual_greeting(user_input):
                prompt = f"""{context}User: {user_input}

Reply casually and naturally like a friend. Keep it short (1-2 sentences)."""
                response, route = route_query(prompt, force_llm=True)
            else:
                response, route = route_query(user_input, context=context)

            add_to_conversation(user_input, response)
            add_experience(f"User: {user_input}")

            console.print(f"[bold green]JARVIS:[/bold green] {response}")
            if tts_enabled:
                speak(response)

        except KeyboardInterrupt:
            console.print("\n[bold red]Later, Sir.[/bold red]")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")


if __name__ == "__main__":
    run_jarvis()
