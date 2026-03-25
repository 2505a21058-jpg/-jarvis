import os
import logging
import subprocess
import time
import requests
from dotenv import load_dotenv

os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
logging.getLogger("transformers").setLevel(logging.ERROR)

load_dotenv()

from main import chat, retrieve_memory, search_experience
from skills.router import handle_skill
from rich.console import Console

console = Console()


# ------------------ Personality ------------------
BASE_RULES = """
You are JARVIS.

- Answer only what is asked
- Keep responses short
- Do not guess
"""


# ------------------ Intent Detection ------------------
def detect_intent(text):
    text = text.lower()

    if "what do i like" in text:
        return "memory"

    if any(w in text for w in [
        "error", "issue", "not working", "blocked", "stuck", "problem"
    ]):
        return "experience"

    if any(cmd in text for cmd in ["open", "play", "search", "order"]):
        return "skill"

    if any(w in text for w in ["who", "what", "tell me", "latest"]):
        return "web"

    return "chat"


# ------------------ Web ------------------
def web_search(query):
    try:
        url = f"https://api.duckduckgo.com/?q={query}&format=json"
        res = requests.get(url).json()

        if res.get("AbstractText"):
            return res["AbstractText"]

        return "I don't know."

    except:
        return "I don't know."


# ------------------ System ------------------
def start_ollama_engine():
    try:
        requests.get("http://127.0.0.1:11434")
    except:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        time.sleep(5)


# ------------------ Main Loop ------------------
def run_jarvis():
    start_ollama_engine()

    console.print("[bold green]JARVIS Online[/bold green]\n")

    while True:
        user_input = input("You: ").strip()

        if not user_input:
            continue

        intent = detect_intent(user_input)

        # ------------------ EXPERIENCE FIRST ------------------
        if intent == "experience":
            result = search_experience(user_input)

            if result:
                response = result
            else:
                response = "I don't have a known solution for this yet."

        # ------------------ MEMORY ------------------
        elif intent == "memory":
            mem = retrieve_memory(user_input)
            response = f"You mentioned: {mem[0]}" if mem else "No memory found."

        # ------------------ SKILL ------------------
        elif intent == "skill":
            response = handle_skill(user_input) or "Done."

        # ------------------ WEB ------------------
        elif intent == "web":
            response = web_search(user_input)

        # ------------------ CHAT ------------------
        else:
            response = chat(user_input, BASE_RULES)

        console.print(f"[bold green]JARVIS:[/bold green] {response}\n")


# ------------------ Run ------------------
if __name__ == "__main__":
    run_jarvis()