import os
import logging
import subprocess
import time
import requests
from dotenv import load_dotenv

# Silence logs immediately
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

load_dotenv()

import ollama
from main import chat, get_personality_choice, PERSONALITIES, conversation_history
from voice import speak
from skills.router import handle_skill
from rich.console import Console
from rich.panel import Panel

from memory.core import (
    load_profile,
    save_profile,
    add_experience,
    get_all_facts,
    semantic_search
)

console = Console()
tts_enabled = False

PERSONALITIES = {
    "1": {"name": "Normal", "prompt": "You are JARVIS, a helpful, intelligent, and friendly AI assistant. Be clear, direct, and natural."},
    "2": {"name": "JARVIS", "prompt": "You are JARVIS, a helpful, intelligent, and casual AI assistant living digitally. Speak naturally like a smart friend. Use user memories only when they are relevant to the question. Do not force memories into every reply."},
    "3": {"name": "Funny", "prompt": "You are JARVIS, a helpful and lightly funny AI assistant. Be witty but accurate. Use user memories only when relevant."},
    "4": {"name": "Desi", "prompt": "You are JARVIS, a helpful AI assistant with a desi vibe. Speak naturally in Hinglish when it fits. Be friendly and useful. Use user memories only when relevant."}
}

def start_ollama_engine():
    print("[System] Initializing RTX 4050 and starting Ollama...")
    # Force the NVIDIA GPU 0 and set context limit to save RAM
    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    os.environ["OLLAMA_NUM_CTX"] = "2048"
    
    # Check if Ollama is already running
    try:
        requests.get("http://127.0.0.1:11434")
        print("[System] Ollama is already active on GPU.")
    except:
        # Start Ollama serve as a background process
        subprocess.Popen(["ollama", "serve"], 
                         stdout=subprocess.DEVNULL, 
                         stderr=subprocess.DEVNULL)
        time.sleep(5)  # Give it a few seconds to wake up
        print("[System] Engine started successfully.")

def preload_model():
    with console.status("[dim]Warming up JARVIS...[/dim]"):
        ollama.chat(model="llama3.2", messages=[{"role": "user", "content": "hi"}])

def build_memory_context(user_input):
    profile = load_profile()
    facts_dict, recent_exps = get_all_facts()
    similar = semantic_search(user_input, top_k=3)

    context = ""

    if facts_dict:
        context += "User facts:\n"
        for v in list(facts_dict.values())[:8]:
            context += f"- {v}\n"

    if recent_exps:
        context += "\nRecent memories:\n"
        for exp in recent_exps[-6:]:
            context += f"- {exp['memory']}\n"

    return context

def run_jarvis():
    global tts_enabled

    # Initialize the GPU Engine first
    start_ollama_engine()

    profile = load_profile()
    name = profile.get("name", "Sir")
    saved_choice = profile.get("preferred_personality", "2")
    current_personality = PERSONALITIES.get(saved_choice, PERSONALITIES["2"])

    console.print(Panel("JARVIS Online", style="bold green"))
    console.print(f"[dim]Commands: speak on/off | shut up | switch | quit | remember ... | what do you remember[/dim]\n")
    console.print(f"[bold green]Welcome back, {name}.[/bold green]")
    console.print(f"[bold green]{current_personality['name']} mode active.[/bold green]")
    console.print("[dim]TTS is off by default. Type 'speak on' to enable voice output.[/dim]")

    # preload_model() # Commented out to prevent RAM spikes and redundant calls

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        lower_input = user_input.lower().strip()

        if lower_input in ["speak on", "tts on", "voice on"]:
            tts_enabled = True
            console.print("[bold cyan]Text-to-speech enabled[/bold cyan]")
            speak("Text-to-speech enabled.")
            continue

        if lower_input in ["speak off", "tts off", "voice off"]:
            tts_enabled = False
            console.print("[bold cyan]Text-to-speech disabled[/bold cyan]")
            continue

        if lower_input in ["shut up", "stop speaking", "quiet", "silence", "be quiet"]:
            tts_enabled = False
            console.print("[bold cyan]Speech stopped and TTS disabled.[/bold cyan]")
            continue

        if any(w in lower_input for w in ["quit", "exit", "bye", "goodbye"]):
            if tts_enabled:
                speak("Goodbye.")
            console.print("[bold green]JARVIS:[/bold green] Goodbye!")
            break

        if lower_input == "stop":
            console.print("[bold cyan]Stopped.[/bold cyan]")
            continue

        if lower_input == "switch":
            console.print("\n[bold]Choose personality: 1-Normal 2-JARVIS 3-Funny 4-Desi[/bold]")
            choice = get_personality_choice()
            profile = load_profile()
            profile["preferred_personality"] = choice
            save_profile(profile)
            current_personality = PERSONALITIES[choice]
            conversation_history.clear()
            msg = f"Switched to {current_personality['name']} mode."
            console.print(f"[bold green]{msg}[/bold green]\n")
            if tts_enabled: speak(msg)
            continue

        if lower_input.startswith(("remember that ", "remember ")):
            fact = user_input[len("remember that "):].strip() if lower_input.startswith("remember that ") else \
                   user_input[len("remember "):].strip()
            if not fact:
                if tts_enabled: speak("Remember what exactly?")
                console.print("[bold green]JARVIS:[/bold green] Remember what exactly?\n")
                continue

            profile = load_profile()
            short_key = fact[:60].rstrip(" .,!?").strip()
            profile["facts"][short_key] = fact
            save_profile(profile)
            add_experience(f"User told me: {fact}")
            
            msg = f"Got it. '{fact}' saved permanently."
            console.print(f"[bold green]JARVIS:[/bold green] {msg}\n")
            if tts_enabled: speak(msg)
            continue

        if any(phrase in lower_input for phrase in ["what do you remember", "tell me what you know about me", "who am i to you", "recall"]):
            profile = load_profile()
            facts_dict, recent_exps = get_all_facts()
            similar = semantic_search(user_input, top_k=5)

            lines = [f"You are {name}."]
            if profile.get("home_city"):
                lines.append(f"Based in {profile['home_city']}.")

            if facts_dict:
                lines.append("\nKnown facts:")
                for v in list(facts_dict.values())[:8]:
                    lines.append(f"  • {v}")

            if recent_exps or similar:
                lines.append("\nMemories:")
                for exp in recent_exps[-6:]:
                    lines.append(f"  • {exp['memory']}")
                for s in similar:
                    lines.append(f"  • Similar: {s}")

            response = "\n".join(lines) or "I don't have much memory stored yet."
            console.print(f"[bold green]JARVIS:[/bold green] {response}\n")
            if tts_enabled: speak(response)
            continue

        # Main conversation
        memory_context = build_memory_context(user_input)

        enhanced_prompt = f"""You are JARVIS, a helpful, intelligent, and natural AI assistant.

RULES:
- Be casual and friendly.
- Use memories ONLY when they are relevant to the current question.
- Do not force memories into every reply.
- Keep responses short and natural.

MEMORY CONTEXT:
{memory_context}

User: {user_input}"""

        skill_response = handle_skill(user_input)

        if skill_response:
            clean = " ".join(skill_response.split())
            console.print(f"[bold green]JARVIS:[/bold green] {clean}\n")
            if tts_enabled: speak(clean)
        else:
            with console.status("[bold green]JARVIS is thinking...[/bold green]"):
                response = chat(enhanced_prompt, current_personality["prompt"])
            clean = " ".join(response.split())
            console.print(f"[bold green]JARVIS:[/bold green] {clean}\n")
            if tts_enabled: speak(clean)

if __name__ == "__main__":
    run_jarvis()