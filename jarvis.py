import os
import subprocess
import time
from dotenv import load_dotenv
load_dotenv()

import ollama
from voice import speak
from skills.router import process_query, handle_skill
from rich.console import Console
from rich.panel import Panel

from memory.core import (
    load_profile,
    save_profile,
    add_fact,
    add_experience,
    get_facts,
    get_recent_experiences,
    semantic_search
)

console = Console()
tts_enabled = False

# Session history for continuity
conversation_history = []

def start_ollama():
    try:
        ollama.chat(model="llama3.2", messages=[{"role": "user", "content": "test"}])
    except:
        console.print("[yellow]Starting Ollama server...[/yellow]")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)

def run_jarvis():
    global tts_enabled

    start_ollama()

    profile = load_profile()
    name = profile.get("name", "Sir")

    console.print(Panel("JARVIS Online", style="bold green"))
    console.print("[dim]Commands: speak on/off | shut up | quit | remember ... | what do you remember | switch[/dim]\n")
    console.print(f"[bold green]Welcome back, {name}.[/bold green]")
    console.print("[bold green]JARVIS mode active.[/bold green]")
    console.print("[dim]TTS is off by default. Type 'speak on' to enable voice output.[/dim]")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        lower_input = user_input.lower().strip()

        # TTS Controls
        if lower_input in ["speak on", "tts on", "voice on"]:
            tts_enabled = True
            console.print("[bold cyan]Text-to-speech enabled[/bold cyan]")
            speak("Text-to-speech enabled.")
            continue

        if lower_input in ["speak off", "tts off", "voice off"]:
            tts_enabled = False
            console.print("[bold cyan]Text-to-speech disabled[/bold cyan]")
            continue

        if lower_input in ["shut up", "stop speaking", "quiet", "silence"]:
            tts_enabled = False
            console.print("[bold cyan]Speech stopped.[/bold cyan]")
            continue

        if any(w in lower_input for w in ["quit", "exit", "bye", "goodbye"]):
            if tts_enabled: speak("Goodbye Sir.")
            console.print("[bold green]JARVIS:[/bold green] Goodbye!")
            conversation_history.clear()
            break

        # Memory Store
        if "remember that" in lower_input or lower_input.startswith("remember "):
            fact = user_input.replace("remember that ", "").replace("remember ", "").strip()
            key = fact[:60].rstrip(" .,!?").strip()
            add_fact(key, fact)
            add_experience(f"User told me: {fact}")
            msg = f"Got it. '{fact}' saved permanently."
            console.print(f"[bold green]JARVIS:[/bold green] {msg}\n")
            if tts_enabled: speak(msg)
            continue

        # Memory Retrieve
        if any(word in lower_input for word in ["what do you remember", "tell me what you know", "who am i", "recall"]):
            facts = get_facts()
            experiences = get_recent_experiences()

            lines = [f"You are {name}."]
            if facts:
                lines.append("\nKnown facts:")
                for k, v in list(facts.items())[:8]:
                    lines.append(f"  • {v}")
            if experiences:
                lines.append("\nRecent memories:")
                for exp in experiences[-6:]:
                    lines.append(f"  • {exp['memory']}")

            response = "\n".join(lines) or "I don't have much memory stored yet."
            console.print(f"[bold green]JARVIS:[/bold green] {response}\n")
            if tts_enabled: speak(response)
            continue

        # Skill Handling
        skill_response = handle_skill(user_input)
        if skill_response:
            clean = " ".join(skill_response.split())
            console.print(f"[bold green]JARVIS:[/bold green] {clean}\n")
            if tts_enabled: speak(clean)
            continue

        # Light but effective context for continuity
        memory_context = ""
        facts = get_facts()
        if facts:
            memory_context += "User facts: " + ", ".join(list(facts.values())[:5]) + "\n"

        experiences = get_recent_experiences(5)
        if experiences:
            memory_context += "Recent: " + " | ".join([exp['memory'][:90] for exp in experiences]) + "\n"

        system_prompt = f"""You are JARVIS, a helpful, intelligent, and casual AI assistant.
Speak naturally like a smart friend.
Be accurate and useful.
Use the following user memories only when they are relevant:
{memory_context}
Keep responses natural and concise."""

        with console.status("[bold green]JARVIS is thinking...[/bold green]"):
            response, route_info = process_query(user_input)

        # Keep session history for better continuity
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response})
        if len(conversation_history) > 8:
            conversation_history.pop(0)
            conversation_history.pop(0)

        console.print(f"[bold green]JARVIS:[/bold green] {response}\n")
        if tts_enabled:
            speak(response)

if __name__ == "__main__":
    run_jarvis()