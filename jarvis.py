import asyncio
import importlib.util
import logging
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime

import psutil

from utils.logging_setup import setup_logging

setup_logging()

# Log buffer: captures log records during input() to prevent console interleaving
_input_session_active = False
_input_buffer: list[logging.LogRecord] = []
_input_buffer_lock = threading.Lock()


def _install_input_buffer() -> None:
    """Wrap the root console StreamHandler to buffer records during input()."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr:
            original_emit = handler.emit

            def buffered_emit(
                record: logging.LogRecord,
                _orig=original_emit,
            ) -> None:
                if _input_session_active and record.levelno < logging.ERROR:
                    with _input_buffer_lock:
                        _input_buffer.append(record)
                else:
                    _orig(record)

            handler.emit = buffered_emit
            break


def _flush_input_buffer() -> None:
    """Flush buffered log records to stdout between input cycles."""
    global _input_buffer
    with _input_buffer_lock:
        records = _input_buffer
        _input_buffer = []
    if records:
        sys.stdout.write("\n")
        for r in records:
            ts = datetime.fromtimestamp(r.created).strftime("%H:%M:%S")
            sys.stdout.write(
                f"{ts} {r.levelname:<8} {r.name:<24} {r.getMessage()}\n"
            )
        sys.stdout.flush()


_install_input_buffer()

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

try:
    import msvcrt
except ImportError:
    msvcrt = None  # not Windows; _poll_input will fall back to input()

from agent.loop import run_agent_cycle
from agent.state import State
from memory.core import Memory
from memory.context_adapter import set_state_ref
from model_manager import model_manager
from agent.gate import get_gate
from skills import bootstrap_skills
from skills.learned import register_learned_skills
from memory.promoter import PromotionScheduler
from jconfig import get_config

cfg = get_config()

from config import (
    OLLAMA_READY_POLL_INTERVAL_SECONDS,
    OLLAMA_READY_POLL_TIMEOUT_SECONDS,
    OLLAMA_READY_TIMEOUT_SECONDS,
    OLLAMA_TAGS_URL,
)

# CLI tab completion
try:
    import readline
    _COMMANDS = [
        "speak on", "speak off", "fast mode", "smart mode", "nerd mode",
        "quit", "exit", "bye", "remember ", "/voice",
    ]
    def _completer(text, state):
        options = [c for c in _COMMANDS if c.startswith(text)]
        return options[state] if state < len(options) else None
    readline.parse_and_bind("tab: complete")
    readline.set_completer(_completer)
except ImportError:
    pass


logger = logging.getLogger("jarvis.main")
startup_logger = logging.getLogger("jarvis.startup")

load_dotenv()

console = Console()
tts_enabled = False
def _web_enabled() -> bool:
    return os.environ.get("JARVIS_WEB", "").lower() in {"1", "true", "yes"}

MODE_COMMANDS = {
    "fast mode": "fast",
    "normal mode": "fast",
    "smart mode": "smart",
    "nerd mode": "nerd",
    "deep mode": "nerd",
}

_PREFERRED_MODELS = [
    "qwen3:8b",
    "qwen3:14b",
    "mistral:latest",
    "llama3.2:3b",
    "llama3.2:latest",
    "jarvis-core:latest",
]


def _configure_default_model_env() -> None:
    """Set startup model defaults when the user has not provided overrides."""
    if not os.environ.get("JARVIS_MODEL"):
        os.environ["JARVIS_MODEL"] = cfg.llm.main_model
    if not os.environ.get("JARVIS_ACTION_MODEL"):
        os.environ["JARVIS_ACTION_MODEL"] = cfg.llm.fast_model
    if not os.environ.get("JARVIS_EMBED_MODEL"):
        os.environ["JARVIS_EMBED_MODEL"] = cfg.llm.embed_model


def _select_best_model(available_models: list[str]) -> str:
    """Select best available model from preference list."""
    available_lower = [str(model).lower() for model in available_models]
    for preferred in _PREFERRED_MODELS:
        preferred_key = preferred.replace(":", "").lower()
        for idx, available in enumerate(available_lower):
            if preferred_key in available.replace(":", ""):
                logger.info(
                    "Selected model: %s (from preference list)",
                    available_models[idx],
                )
                return available_models[idx]
    return available_models[0] if available_models else "llama3.2:3b"


def _print_startup_readiness(
    ollama_models: list[str],
    active_model: str,
    memory_count: int,
    semantic_memory_ok: bool,
    remote_bridge_enabled: bool,
    bridge_token_set: bool,
    telegram_token_set: bool,
    websockets_ok: bool,
    playwright_ok: bool,
    chrome_ready: bool,
    chrome_profile: str,
    psutil_ok: bool,
    pdfplumber_ok: bool,
    smtp_set: bool,
    llava_ok: bool,
    mss_ok: bool,
    rawvision_elements: int,
    rawvision_layers: list[str],
    rawvision_ms: float,
    hands_ok: bool,
    web_enabled: bool = False,
) -> int:
    """Print startup readiness. Returns count of not-configured items."""
    from models.model_router import get_action_model, get_embed_model

    action_model = get_action_model()
    embed_model = get_embed_model()

    action_available = any(
        action_model.split(":")[0].lower() in model.lower()
        for model in ollama_models
    )
    embed_available = any(
        embed_model.split(":")[0].lower() in model.lower()
        for model in ollama_models
    )

    not_configured = 0

    print()
    print("=" * 58)
    print("  JARVIS STARTUP READINESS")
    print("=" * 58)

    print()
    print("[MODELS]")
    print(f"  [OK] Main model          {active_model}")

    if action_available:
        print(f"  [OK] Action model        {action_model}  (automation + vision)")
    else:
        print(f"  [--] Action model        {action_model}  run: ollama pull {action_model}")
        not_configured += 1

    if embed_available:
        print(f"  [OK] Embed model         {embed_model}")
    else:
        print(f"  [--] Embed model         {embed_model}  run: ollama pull {embed_model}")
        not_configured += 1

    available_str = ", ".join(model.split(":")[0] for model in ollama_models[:6])
    print(f"  [INFO] Available         {available_str}")

    print()
    print("[MEMORY]")
    print(f"  [OK] Memory entries      {memory_count:,} entries indexed")
    if semantic_memory_ok:
        print(f"  [OK] Semantic memory     {embed_model}  active")
    else:
        print("  [--] Semantic memory     Not available")
        not_configured += 1

    print()
    print("[BROWSER]")
    if playwright_ok:
        print("  [OK] Playwright          Available")
    else:
        print("  [--] Playwright          Not installed")
        not_configured += 1



    if chrome_ready:
        print(f"  [OK] Chrome harness      Port 9222 ready  |  Profile: {chrome_profile}")
    else:
        print(f"  [--] Chrome harness      Launching in background  |  Profile: {chrome_profile}")

    print()
    print("[VISION]")
    if llava_ok:
        print("  [OK] Vision model        llava  (screenshot analysis)")
    else:
        print("  [--] Vision model        llava not available")

    if action_available:
        print(f"  [OK] Gemma3 vision       {action_model}  (computer use decisions)")
    else:
        print(f"  [--] Gemma3 vision       {action_model} not pulled")

    if mss_ok:
        print("  [OK] Screen capture      mss  installed")
    else:
        print("  [--] Screen capture      mss not installed")
        not_configured += 1

    print()
    print("[RAWVISION]")
    if rawvision_elements > 0:
        layers_str = ", ".join(rawvision_layers) if rawvision_layers else "none"
        print(
            "  [OK] Screen reading      "
            f"{rawvision_elements} elements  |  layers: {layers_str}  |  {rawvision_ms:.0f}ms"
        )
    else:
        print("  [--] Screen reading      No elements captured")
        not_configured += 1

    print()
    print("[HANDS]")
    if hands_ok:
        print("  [OK] Automation          Terminal + UIA + WinAPI + CDP engines ready")
    else:
        print("  [!!] Automation          Hands initialization failed")

    print()
    print("[REMOTE BRIDGE]")
    if remote_bridge_enabled:
        print("  [OK] Remote bridge       Enabled")
        if websockets_ok:
            print("  [OK] WebSocket           ws://127.0.0.1:8765")
        else:
            print("  [!!] WebSocket           websockets not installed  pip install websockets")
            not_configured += 1
        if bridge_token_set:
            print("  [OK] Bridge token        Set")
        else:
            print("  [!!] Bridge token        Not set  set JARVIS_BRIDGE_TOKEN")
            not_configured += 1
        if telegram_token_set:
            print("  [OK] Telegram            Bot token set")
        else:
            print("  [--] Telegram            Not configured  (optional)")
    else:
        print("  [--] Remote bridge       Disabled")

    print()
    print("[WEB UI]")
    fastapi_ok = importlib.util.find_spec("fastapi") is not None
    uvicorn_ok = importlib.util.find_spec("uvicorn") is not None
    if web_enabled:
        if fastapi_ok and uvicorn_ok:
            print("  [OK] Web server           http://127.0.0.1:9090")
        else:
            missing = []
            if not fastapi_ok:
                missing.append("fastapi")
            if not uvicorn_ok:
                missing.append("uvicorn")
            print(f"  [!!] Web server           Missing: {', '.join(missing)}  pip install {' '.join(missing)}")
            not_configured += 1
    else:
        print("  [--] Web server           Disabled  (pass --web to enable)")

    print()
    print("[OPTIONAL SKILLS]")
    if psutil_ok:
        print("  [OK] psutil              System monitor  installed")
    else:
        print("  [--] psutil              pip install psutil")
        not_configured += 1

    if pdfplumber_ok:
        print("  [OK] pdfplumber          PDF reading  installed")
    else:
        print("  [--] pdfplumber          pip install pdfplumber")

    if smtp_set:
        print("  [OK] SMTP                Email sending  configured")
    else:
        print("  [--] SMTP                Not configured  (optional)")

    print()
    print("=" * 58)
    if not_configured == 0:
        print("  [OK] All systems ready")
    else:
        print("  [OK] Core systems ready")
        print(f"  [--] {not_configured} item(s) need attention")
    print("=" * 58)
    print()

    return not_configured


def start_ollama():
    try:
        logger.info("Starting Ollama service")
        console.print("[dim]Warming up local model...[/dim]")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.exception("Failed to start Ollama: %s", exc)
        console.print(f"[bold red]Failed to start Ollama: {exc}[/bold red]")


def _wait_for_ollama(timeout: float = OLLAMA_READY_TIMEOUT_SECONDS) -> bool:
    """Poll Ollama health endpoint instead of sleeping blindly."""
    import requests

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            # Ollama readiness now uses shared config so startup works with custom hosts.
            response = requests.get(OLLAMA_TAGS_URL, timeout=OLLAMA_READY_POLL_TIMEOUT_SECONDS)
            if response.status_code == 200:
                logger.info("Ollama is ready")
                return True
        except requests.ConnectionError:
            # Connection refusals are expected during startup but logged for readiness diagnosis.
            logger.debug("Ollama readiness connection refused")
        except Exception as exc:
            logger.debug("Waiting for Ollama readiness: %s", exc)
        time.sleep(OLLAMA_READY_POLL_INTERVAL_SECONDS)
    logger.error("Ollama did not become ready in time")
    return False


def warmup_startup_models():
    try:
        model_manager.warm_startup_models()
    except Exception as exc:
        logger.warning("Model warmup warning: %s", exc)
        console.print(f"[dim]Model warmup warning: {exc}[/dim]")


def _profile_name(memory: Memory) -> str:
    """
    Get user's name from memory profile.
    Returns empty string if not found; caller handles the greeting format.
    """
    try:
        results = memory.retrieve("user profile name", mode="fast", limit=3)
        if not results:
            return ""

        for entry in results:
            content = str(entry.get("content", ""))
            patterns = [
                r"(?:my name is|i am|i'm|call me)\s+([A-Z][a-z]+)\b",
                r"name:\s*([A-Z][a-z]+)\b",
                r"user:\s*([A-Z][a-z]+)\b",
            ]
            for pattern in patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    return match.group(1)

        profile_results = memory.retrieve("profile", mode="fast", limit=1)
        if profile_results:
            profile = profile_results[0].get("profile", {})
            if isinstance(profile, dict):
                name = str(profile.get("name", "")).strip()
                if name:
                    return name
    except Exception as e:
        logger.debug("Profile name lookup failed: %s", e)
    return ""


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
        from agent.executor import get_executor

        get_executor().shutdown()
    except Exception as exc:
        logger.warning("Executor shutdown warning: %s", exc)

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


async def _poll_input(
    running_task: asyncio.Task | None = None,
) -> str | None:
    """
    Read user input using msvcrt polling (non-blocking, cancellable on Windows).

    Args:
        running_task: If provided, also polls for task completion.
                      Returns None if the task completes before Enter.

    Returns:
        str: the input line when user presses Enter
        None: if running_task completed before input was submitted
    """
    global _input_session_active
    _input_session_active = True
    try:
        if msvcrt is None:
            # Non-Windows fallback — plain input()
            user_input = input("You: ")
            return user_input

        chars: list[str] = []
        if running_task is None:
            sys.stdout.write("You: ")
            sys.stdout.flush()

        while True:
            if running_task is not None and running_task.done():
                if chars:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                return None

            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch == "\r":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "".join(chars)
                if ch == "\x03":
                    raise KeyboardInterrupt
                if ch in ("\b", "\x7f"):
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif ch == "\xe0":
                    msvcrt.getwch()
                elif ch >= " ":
                    chars.append(ch)
                    sys.stdout.write(ch)
                    sys.stdout.flush()

            await asyncio.sleep(0.05)
    finally:
        _input_session_active = False
        _flush_input_buffer()


async def run_jarvis():
    global tts_enabled
    had_model_env = bool(os.environ.get("JARVIS_MODEL"))
    _configure_default_model_env()
    _available_models: list[str] = []
    _active_model = os.environ.get("JARVIS_MODEL", "qwen3:8b")

    startup_logger.info(
        "Jarvis starting | OS=%s %s | Python=%s | CPU=%s cores | RAM=%sGB",
        platform.system(),
        platform.release(),
        platform.python_version(),
        psutil.cpu_count(),
        psutil.virtual_memory().total // (1024**3),
    )

    start_ollama()
    if not _wait_for_ollama(timeout=OLLAMA_READY_TIMEOUT_SECONDS):
        logger.warning("Proceeding without confirmed Ollama readiness")

    try:
        from models.model_manager import get_available_models

        _available_models = get_available_models()
        _active_model = (
            os.environ.get("JARVIS_MODEL", "")
            if had_model_env
            else _select_best_model(_available_models)
        )
        if not had_model_env:
            os.environ["JARVIS_MODEL"] = _active_model
        model_manager.models["fast"] = _active_model
        logger.info("Active model: %s", _active_model)
        logger.info("Available models: %s", ", ".join(_available_models[:5]))
    except Exception as exc:
        logger.debug("Model auto-detection skipped: %s", exc)

    try:
        from playwright.async_api import async_playwright  # noqa: F401

        logger.info("Playwright available")
    except ImportError:
        logger.warning(
            "Playwright not installed. Browser skills will use OS fallback.\n"
            "Fix: pip install playwright && python -m playwright install chromium"
        )

    memory = Memory()
    pruned = memory.prune()
    if pruned:
        logger.info("Pruned %s expired memories at startup", pruned)

    _semantic_memory_ok = memory.is_semantic_available()
    if _semantic_memory_ok:
        logger.info("Semantic memory: ENABLED (nomic-embed-text)")
    else:
        logger.info("Semantic memory: DISABLED - run 'ollama pull nomic-embed-text' to enable")

    state = State(mode="fast")
    set_state_ref(state)

    bootstrap_skills()

    if len(memory._experience_index._entries) > 900:
        memory.prune_experiences(max_entries=700)
    register_learned_skills(memory)

    from agent.intent.learned_rules import load_all_learned_rules

    rules_loaded = load_all_learned_rules(memory)
    logger.info("Loaded %s learned skill gate rules", rules_loaded)

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

    # Chrome harness pre-launch (synchronous — completes before user input)
    try:
        from agent.harness.launcher import ensure_chrome_debug

        ready = ensure_chrome_debug()
        if ready:
            logger.info(
                "Chrome harness ready (profile: jarvis / Profile 3)"
            )
        else:
            logger.warning(
                "Chrome harness not available. "
                "Browser skills will use Playwright fallback."
            )
    except Exception as e:
        logger.warning("Chrome pre-launch failed: %s", e)

    warmup_startup_models()
    heartbeat = None
    remote_bridge = None

    _heartbeat_enabled = cfg.heartbeat.enabled
    _heartbeat_interval = cfg.heartbeat.interval_seconds

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

    _remote_enabled = cfg.remote.enabled
    if _remote_enabled:
        try:
            from interfaces.remote_bridge import RemoteBridge

            _bridge = RemoteBridge(memory, state)
            _bridge.start(
                enable_telegram=bool(cfg.remote.telegram_bot_token),
                enable_websocket=True,
            )
            remote_bridge = _bridge
            logger.info("Remote bridge started")
        except Exception as exc:
            logger.error("Remote bridge failed to start (non-critical): %s", exc)
    else:
        logger.info("Remote bridge disabled. Enable in jconfig.yaml or set JARVIS_REMOTE_BRIDGE=true.")

    # Web interface startup
    if _web_enabled():
        try:
            from interfaces.web.app import start_web_server
            start_web_server(memory, state, host="127.0.0.1", port=9090)
        except Exception as e:
            logger.warning("Web UI failed to start: %s", e)

    try:
        memory_count = len(getattr(memory._experience_index, "_entries", ()))

        from agent.harness.launcher import _CHROME_PROFILE, is_chrome_debug_available

        chrome_ready = is_chrome_debug_available()

        chrome_profile = _CHROME_PROFILE

        rawvision_elements = 0
        rawvision_layers: list[str] = []
        rawvision_ms = 0.0
        try:
            from rawvision import RawVision

            ctx = RawVision.capture()
            rawvision_elements = len(ctx.elements)
            rawvision_layers = [
                getattr(layer, "value", str(layer))
                for layer in ctx.layers_used
            ]
            rawvision_ms = ctx.capture_ms
        except Exception as rawvision_exc:
            logger.debug("RawVision startup check skipped: %s", rawvision_exc)

        hands_ok = False
        try:
            from agent.hands.engines.terminal_engine import TerminalEngine

            hands_ok, _hands_out = TerminalEngine().run(
                "echo hands_ok",
                timeout=5,
            )
        except Exception as hands_exc:
            logger.debug("Hands startup check skipped: %s", hands_exc)

        model_bases = {model.split(":")[0].lower() for model in _available_models}
        _print_startup_readiness(
            ollama_models=_available_models,
            active_model=_active_model,
            memory_count=memory_count,
            semantic_memory_ok=_semantic_memory_ok,
            remote_bridge_enabled=_remote_enabled,
            bridge_token_set=bool(cfg.remote.bridge_token),
            telegram_token_set=bool(cfg.remote.telegram_bot_token),
            websockets_ok=importlib.util.find_spec("websockets") is not None,
            playwright_ok=importlib.util.find_spec("playwright") is not None,
            chrome_ready=chrome_ready,
            chrome_profile=chrome_profile,
            psutil_ok=importlib.util.find_spec("psutil") is not None,
            pdfplumber_ok=importlib.util.find_spec("pdfplumber") is not None,
            smtp_set=bool(cfg.smtp.host),
            llava_ok="llava" in model_bases,
            mss_ok=importlib.util.find_spec("mss") is not None,
            rawvision_elements=rawvision_elements,
            rawvision_layers=rawvision_layers,
            rawvision_ms=rawvision_ms,
            hands_ok=hands_ok,
            web_enabled=_web_enabled(),
        )
    except Exception as exc:
        logger.debug("Readiness display error (non-critical): %s", exc)

    console.print(Panel("JARVIS Online", style="bold green"))
    name = _profile_name(memory)
    if name:
        console.print(f"[bold green]Welcome back, {name}.[/bold green]\n")
    else:
        console.print("[bold green]Jarvis Online.[/bold green]\n")

    cycle = 0

    current_task: asyncio.Task | None = None

    while True:
        try:
            user_input = await _poll_input(current_task)

            # --- Task completed during input polling ---
            if user_input is None:
                if current_task is not None:
                    try:
                        _flush_input_buffer()
                        result, evaluation, _, state = current_task.result()
                        response = str(result.get("output") or "").strip()
                        if not response:
                            response = "I couldn't produce a useful response."
                        console.print(f"[bold green]JARVIS:[/bold green] {response}")
                        if tts_enabled:
                            _speak(response)
                        if evaluation.get("error"):
                            console.print(f"[dim]Execution note: {evaluation['error']}[/dim]")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error("Unhandled error in agent cycle: %s", e, exc_info=True)
                        console.print("[bold green]JARVIS:[/bold green] Something went wrong on my end. I've logged the error. Please try again.")
                    finally:
                        current_task = None
                continue

            # --- Parse input ---
            user_input = user_input.strip()
            if not user_input:
                continue

            lower = user_input.lower()

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

            # --- Cancel any in-flight task before starting a new one ---
            if current_task is not None and not current_task.done():
                current_task.cancel()
                try:
                    await current_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass  # Task had an error — we're moving on

            # --- /voice special handling ---
            if lower == "/voice":
                try:
                    from voice import listen
                    voice_input = listen()
                    if voice_input:
                        console.print(f"[dim]You (voice): {voice_input}[/dim]")
                        user_input = voice_input
                    else:
                        console.print("[dim]Voice input failed or timed out[/dim]")
                        continue
                except Exception as e:
                    console.print(f"[dim]Voice error: {e}[/dim]")
                    continue

            # --- Launch agent cycle as a background task ---
            cycle += 1
            current_task = asyncio.create_task(
                run_agent_cycle(
                    user_input,
                    memory,
                    state,
                    emit_trace=False,
                    cycle=cycle,
                )
            )
            # Do NOT await — polling in the next _poll_input() call
            # will either detect completion or preempt with new input.

        except EOFError:
            logger.info("Jarvis input stream closed")
            break
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


def main() -> None:
    """Entry point for `jarvis` console script."""
    if "--web" in sys.argv:
        os.environ["JARVIS_WEB"] = "true"
    asyncio.run(run_jarvis())


if __name__ == "__main__":
    main()
