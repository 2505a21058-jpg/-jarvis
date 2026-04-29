import logging
import os
import re
import subprocess
import sys
import time

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv():
        return False

try:
    from rich.console import Console
    from rich.panel import Panel
except ModuleNotFoundError:
    class Console:
        def print(self, *args, **kwargs):
            print(*args)

    def Panel(text, style=None):
        _ = style
        return text

from agent.loop import run_agent_cycle
from agent.state import State
from memory.core import Memory
from memory.context_adapter import set_state_ref
from model_manager import model_manager
from agent.gate import get_gate
from skills import bootstrap_skills
from skills.learned import register_learned_skills
from memory.promoter import PromotionScheduler


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("jarvis.log", mode="a", encoding="utf-8"),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


configure_logging()
logger = logging.getLogger("jarvis.main")

load_dotenv()

console = Console()
tts_enabled = False

MODE_COMMANDS = {
    "fast mode": "fast",
    "normal mode": "fast",
    "smart mode": "smart",
    "nerd mode": "nerd",
    "deep mode": "nerd",
}


def start_ollama():
    try:
        logger.info("Starting Ollama service")
        console.print("[dim]Warming up local model...[/dim]")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.exception("Failed to start Ollama: %s", exc)
        console.print(f"[bold red]Failed to start Ollama: {exc}[/bold red]")


def _wait_for_ollama(timeout: float = 10.0) -> bool:
    """Poll Ollama health endpoint instead of sleeping blindly."""
    import requests

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=1.0)
            if response.status_code == 200:
                logger.info("Ollama is ready")
                return True
        except requests.ConnectionError:
            pass
        except Exception as exc:
            logger.debug("Waiting for Ollama readiness: %s", exc)
        time.sleep(0.5)
    logger.error("Ollama did not become ready in time")
    return False


def warmup_startup_models():
    try:
        model_manager.warm_startup_models()
    except Exception as exc:
        logger.warning("Model warmup warning: %s", exc)
        console.print(f"[dim]Model warmup warning: {exc}[/dim]")


def _profile_name(memory: Memory) -> str:
    profile = memory.retrieve("", mode="fast").get("profile", {})
    name = str(profile.get("name", "")).strip()
    return name or "there"


def _remember_fact(memory: Memory, fact_text: str):
    fact = fact_text.strip()
    if not fact:
        return

    name_match = re.search(r"\bmy name is\s+(.+)$", fact, re.IGNORECASE)
    if name_match:
        memory.store({"name": name_match.group(1).strip()})
        return

    key = fact[:60].strip().lower() or "fact"
    memory.store({"facts": {key: fact}})


def shutdown_jarvis():
    try:
        from skills.browser import close_browser

        close_browser()
    except Exception as exc:
        logger.warning("Browser shutdown warning: %s", exc)
        console.print(f"[dim]Browser shutdown warning: {exc}[/dim]")


def _speak(text: str) -> None:
    try:
        from voice import speak

        speak(text)
    except Exception as exc:
        logger.warning("Voice output unavailable: %s", exc)


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def run_jarvis():
    global tts_enabled

    start_ollama()
    if not _wait_for_ollama(timeout=10.0):
        logger.warning("Proceeding without confirmed Ollama readiness")

    memory = Memory()
    state = State(mode="fast")
    set_state_ref(state)

    bootstrap_skills()

    if len(memory._experience_index._entries) > 900:
        memory.prune_experiences(max_entries=700)
    register_learned_skills(memory)

    _promoter = PromotionScheduler(memory, min_importance=0.85)
    startup_promoted = _promoter.run_now()
    logger.info("Startup promotion sweep: %s entries moved to long_term", startup_promoted)
    _promoter.start()

    from agent.gate_rule_generator import load_rules_from_disk

    _loaded_rules = load_rules_from_disk()
    _gate = get_gate()
    for rule in _loaded_rules:
        _gate.add_rule(rule)
    logger.info("Restored %s learned skill gate rules from disk", len(_loaded_rules))
    logger.info("Gate layer initialized")

    warmup_startup_models()
    heartbeat = None
    remote_bridge = None

    _heartbeat_enabled = os.environ.get("JARVIS_HEARTBEAT", "true").lower() == "true"
    _heartbeat_interval = float(os.environ.get("JARVIS_HEARTBEAT_INTERVAL", "600"))

    if _heartbeat_enabled:
        try:
            from agent.heartbeat import HeartbeatLoop

            _heartbeat = HeartbeatLoop(
                memory=memory,
                state=state,
                interval_seconds=_heartbeat_interval,
            )
            _heartbeat.start()
            heartbeat = _heartbeat
            logger.info("Heartbeat loop started (every %.0f min)", _heartbeat_interval / 60)
        except Exception as exc:
            logger.error("Heartbeat loop failed to start (non-critical): %s", exc)

    _remote_enabled = os.environ.get("JARVIS_REMOTE_BRIDGE", "false").lower() == "true"
    if _remote_enabled:
        try:
            from interfaces.remote_bridge import RemoteBridge

            _bridge = RemoteBridge(memory, state)
            _bridge.start(
                enable_telegram=bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
                enable_websocket=True,
            )
            remote_bridge = _bridge
            logger.info("Remote bridge started")
        except Exception as exc:
            logger.error("Remote bridge failed to start (non-critical): %s", exc)
    else:
        logger.info("Remote bridge disabled. Set JARVIS_REMOTE_BRIDGE=true to enable.")

    console.print(Panel("JARVIS Online", style="bold green"))
    console.print(f"[bold green]Welcome back, {_profile_name(memory)}.[/bold green]\n")

    cycle = 0

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            lower = user_input.lower().strip()

            if lower in MODE_COMMANDS:
                new_mode = MODE_COMMANDS[lower]
                if new_mode != state.mode:
                    state.mode = new_mode
                    model_manager.preload_mode_model(new_mode)
                    logger.info("Switched mode to %s", new_mode)
                    console.print(f"[bold cyan]-> Switched to {new_mode.upper()} MODE[/bold cyan]")
                continue

            if lower in {"speak on", "tts on", "voice on"}:
                tts_enabled = True
                logger.info("Voice enabled")
                console.print("[bold cyan]Voice enabled[/bold cyan]")
                continue

            if lower in {"speak off", "tts off", "voice off", "shut up"}:
                tts_enabled = False
                logger.info("Voice disabled")
                console.print("[bold cyan]Voice disabled[/bold cyan]")
                continue

            if lower in {"quit", "exit", "bye"}:
                if tts_enabled:
                    _speak("Later.")
                logger.info("Jarvis shutdown requested by user")
                console.print("[bold red]Later.[/bold red]")
                break

            if lower.startswith("remember "):
                _remember_fact(memory, user_input[9:])
                message = "Got it. I'll keep that in mind."
                console.print(f"[bold green]JARVIS:[/bold green] {message}")
                if tts_enabled:
                    _speak(message)
                continue

            cycle += 1
            result, evaluation, _, state = run_agent_cycle(
                user_input,
                memory,
                state,
                emit_trace=False,
                cycle=cycle,
            )

            response = str(result.get("output") or "").strip()
            if not response:
                response = "I couldn't produce a useful response."

            console.print(f"[bold green]JARVIS:[/bold green] {response}")
            if tts_enabled:
                _speak(response)

            if evaluation.get("error"):
                console.print(f"[dim]Execution note: {evaluation['error']}[/dim]")

        except KeyboardInterrupt:
            logger.info("Jarvis interrupted by user")
            console.print("\n[bold red]Later.[/bold red]")
            break
        except Exception as exc:
            logger.exception("Unhandled error in run_jarvis: %s", exc)
            console.print(f"[bold red]Error:[/bold red] {exc}")

    for service in (heartbeat, remote_bridge, _promoter):
        stopper = getattr(service, "stop", None)
        if callable(stopper):
            try:
                stopper()
            except Exception as exc:
                logger.warning("Service shutdown warning: %s", exc)

    shutdown_jarvis()


if __name__ == "__main__":
    run_jarvis()
