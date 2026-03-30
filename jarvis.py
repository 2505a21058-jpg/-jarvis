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
    add_fact,
    add_experience,
    get_facts,
    get_recent_experiences
)

console = Console()
tts_enabled = False
conversation_history = []

def start_ollama():
    try:
        console.print("[dim]Warming up local model...[/dim]")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(4)
    except:
        pass

def is_casual_greeting(query: str) -> bool:
    q = query.lower().strip()
    casual = ["hi", "hello", "hey", "all gud", "how are you", "sup", "yo", "good morning", "good evening", "namaste"]
    return q in casual or any(g in q for g in casual)

def run_jarvis():
    global tts_enabled, conversation_history

    start_ollama()

    profile = load_profile()
    name = profile.get("name", "Sir")

    console.print(Panel("JARVIS Online", style="bold green"))
    console.print("[dim]Commands: speak on/off | shut up | quit | remember ... | what do you remember[/dim]\n")
    console.print(f"[bold green]Welcome back, {name}.[/bold green]")
    console.print("[bold green]JARVIS mode active.[/bold green]")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            lower = user_input.lower().strip()

            # TTS Controls
            if lower in ["speak on", "tts on", "voice on"]:
                tts_enabled = True
                console.print("[bold cyan]Voice output enabled[/bold cyan]")
                continue
            if lower in ["speak off", "tts off", "voice off", "shut up"]:
                tts_enabled = False
                console.print("[bold cyan]Voice output disabled[/bold cyan]")
                continue

            if lower in ["quit", "exit", "bye"]:
                if tts_enabled: speak("Goodbye Sir.")
                console.print("[bold red]Goodbye, Sir.[/bold red]")
                conversation_history.clear()
                break

            # Memory Commands
            if "remember that" in lower or lower.startswith("remember "):
                fact = user_input.replace("remember that ", "").replace("remember ", "").strip()
                add_fact(fact[:60], fact)
                add_experience(f"User told me: {fact}")
                msg = f"Saved to memory: {fact}"
                console.print(f"[bold green]JARVIS:[/bold green] {msg}")
                if tts_enabled: speak(msg)
                continue

            if any(word in lower for word in ["what do you remember", "recall", "who am i"]):
                facts = get_facts()
                exps = get_recent_experiences()
                response = f"You are {name}."
                if facts:
                    response += "\n\nKnown facts:\n" + "\n".join([f"• {v}" for v in list(facts.values())[:8]])
                if exps:
                    response += "\n\nRecent memories:\n" + "\n".join([f"• {e.get('memory', e)}" for e in exps[-6:]])
                console.print(f"[bold green]JARVIS:[/bold green] {response}")
                if tts_enabled: speak(response)
                continue

            # === STRICT CASUAL GREETING BLOCK - RUNS FIRST ===
            if is_casual_greeting(user_input):
                # Completely bypass all skills and datetime
                history_text = "\n".join([
                    f"User: {m['content']}" if m['role'] == 'user' else f"JARVIS: {m['content']}"
                    for m in conversation_history[-8:]
                ])
                full_prompt = f"""You are JARVIS, a helpful, intelligent, and casual AI assistant.

Recent conversation:
{history_text}

Current user message: {user_input}

Rules for casual greetings:
- Reply warmly and casually like a normal friend.
- Do NOT give time, date, or any factual information.
- Do NOT mention food, potatoes, Venkatesh, or old facts.
- Keep it short and friendly.
- Do not be formal.

Answer:"""

                with console.status("[bold green]JARVIS is thinking...[/bold green]"):
                    response, _ = process_query(full_prompt)

            else:
                # Normal flow for non-casual messages
                skill_response = handle_skill(user_input)
                if skill_response:
                    clean = " ".join(skill_response.split())
                    console.print(f"[bold green]JARVIS:[/bold green] {clean}")
                    if tts_enabled: speak(clean)
                    continue

                facts = get_facts()
                memory_context = ""
                if facts:
                    memory_context = "Relevant user facts: " + ", ".join(list(facts.values())[:4]) + "\n"

                history_text = "\n".join([
                    f"User: {m['content']}" if m['role'] == 'user' else f"JARVIS: {m['content']}"
                    for m in conversation_history[-10:]
                ])

                full_prompt = f"""You are JARVIS, a helpful, intelligent, and casual AI assistant.
Speak naturally like a smart friend. Be accurate and useful.

{memory_context}

Recent conversation:
{history_text}

Current user message: {user_input}

Rules:
- Only use memories if they are directly relevant.
- Continue the conversation naturally.

Answer:"""

                with console.status("[bold green]JARVIS is thinking...[/bold green]"):
                    response, _ = process_query(full_prompt)

            # Update history
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})
            if len(conversation_history) > 15:
                conversation_history = conversation_history[-15:]

            console.print(f"[bold green]JARVIS:[/bold green] {response}")
            if tts_enabled:
                speak(response)

        except KeyboardInterrupt:
            console.print("\n[bold red]Goodbye, Sir.[/bold red]")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {str(e)}")

if __name__ == "__main__":
    run_jarvis()