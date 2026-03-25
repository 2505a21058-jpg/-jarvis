import requests
import subprocess
import time
from rich.console import Console

from memory.core import (
    load_profile,
    add_experience,
    semantic_search
)

import ollama

console = Console()

BASE_RULES = """
You are JARVIS.

- Answer only what is asked
- Keep responses short
- Do not guess
"""

tts_enabled = False


# ------------------ START OLLAMA ------------------
def start_ollama():
    try:
        requests.get("http://127.0.0.1:11434")
    except:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        time.sleep(5)


# ------------------ EXPERIENCE ENGINE ------------------
def check_experience(user_input):
    results = semantic_search(user_input, top_k=3)

    best = None
    best_score = -1

    for r in results:
        if isinstance(r, dict):
            problem = r.get("problem", "").lower()
            score = sum(word in problem for word in user_input.lower().split())

            if score > best_score:
                best = r
                best_score = score

    if best:
        solution = best.get("solution")
        principle = best.get("principle")

        if principle:
            return f"{solution} ({principle})"
        return solution

    return None


# ------------------ CHAT ------------------
def chat(user_input):
    system_message = BASE_RULES

    try:
        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_input}
            ],
            options={"temperature": 0.3}
        )

        return response["message"]["content"]

    except Exception as e:
        return f"Ollama error: {str(e)}"


# ------------------ COMMANDS ------------------
def handle_commands(user_input):
    global tts_enabled

    text = user_input.lower()

    if text == "quit":
        return "EXIT"

    if text == "speak on":
        tts_enabled = True
        return "TTS enabled."

    if text == "speak off":
        tts_enabled = False
        return "TTS disabled."

    return None


# ------------------ MAIN LOOP ------------------
def run_jarvis():
    start_ollama()

    console.print("[bold green]JARVIS Online[/bold green]\n")
    console.print("Commands: speak on/off | quit\n")

    print("Welcome back, Sir.")

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        cmd = handle_commands(user_input)
        if cmd == "EXIT":
            break
        if cmd:
            console.print(f"[bold green]JARVIS:[/bold green] {cmd}\n")
            continue

        # 🔥 EXPERIENCE FIRST
        exp = check_experience(user_input)

        if exp:
            response = exp
        else:
            response = chat(user_input)

            # 🔥 AUTO LEARN (REAL)
            if any(w in user_input.lower() for w in ["error", "issue", "problem", "not working"]):
                add_experience(user_input, response)

        console.print(f"[bold green]JARVIS:[/bold green] {response}\n")


if __name__ == "__main__":
    run_jarvis()