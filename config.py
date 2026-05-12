"""Central runtime configuration for Jarvis."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    # Config loads .env once so optional modules work both inside and outside jarvis.py startup.
    load_dotenv()
except ModuleNotFoundError:
    load_dotenv = None


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


def env_first(*names: str, default: str = "") -> str:
    for name in names:
        value = env_str(name)
        if value:
            return value
    return default


# Shared constants keep runtime endpoints configurable instead of hardcoded per module.
JARVIS_USER_AGENT = env_str("JARVIS_USER_AGENT", "JARVIS/1.0 (personal project)")
OLLAMA_BASE_URL = env_str("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_EMBEDDINGS_URL = f"{OLLAMA_BASE_URL}/api/embeddings"

# Named limits replace scattered magic numbers while keeping existing defaults.
OLLAMA_TAGS_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_TAGS_TIMEOUT", 3.0)
READINESS_HTTP_TIMEOUT_SECONDS = env_float("JARVIS_READINESS_HTTP_TIMEOUT", 2.0)
OLLAMA_READY_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_READY_TIMEOUT", 10.0)
OLLAMA_READY_POLL_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_READY_POLL_TIMEOUT", 1.0)
OLLAMA_READY_POLL_INTERVAL_SECONDS = env_float("JARVIS_OLLAMA_READY_POLL_INTERVAL", 0.5)

# API keys are read from environment variables so credentials are not committed in source.
OPENWEATHER_API_KEY = env_first("OPENWEATHER_API_KEY", "JARVIS_OPENWEATHER_API_KEY")
RAPIDAPI_KEY = env_str("RAPIDAPI_KEY")
REQUEST_TIMEOUT_SECONDS = env_float("JARVIS_REQUEST_TIMEOUT", 10.0)

# Vision and embedding settings are centralized so local model hosts and limits can vary.
VISION_MODEL = env_str("JARVIS_VISION_MODEL", "llava")
VISION_REQUEST_TIMEOUT_SECONDS = env_float("JARVIS_VISION_TIMEOUT", 15.0)
SCREENSHOT_MAX_WIDTH = env_int("JARVIS_SCREENSHOT_MAX_WIDTH", 1024)
EMBED_MODEL = env_str("JARVIS_EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT_SECONDS = env_float("JARVIS_EMBED_TIMEOUT", 5.0)
EMBED_MAX_ENTRIES = env_int("JARVIS_EMBED_MAX_ENTRIES", 1000)
EMBED_INPUT_MAX_CHARS = env_int("JARVIS_EMBED_INPUT_MAX_CHARS", 512)

# First-result automation settings are named so the screen fallback can be tuned safely.
FIRST_RESULT_WAIT_SECONDS = env_float("JARVIS_FIRST_RESULT_WAIT_SECONDS", 3.0)
FIRST_RESULT_CLICK_X_RATIO = env_float("JARVIS_FIRST_RESULT_CLICK_X_RATIO", 0.4)
FIRST_RESULT_CLICK_Y_RATIO = env_float("JARVIS_FIRST_RESULT_CLICK_Y_RATIO", 0.35)

# Notification, SMTP, and editor automation waits are configurable instead of hidden literals.
SMTP_TIMEOUT_SECONDS = env_float("JARVIS_SMTP_TIMEOUT", 10.0)
MONITOR_NOTIFICATION_TIMEOUT_SECONDS = env_int("JARVIS_MONITOR_NOTIFICATION_TIMEOUT", 10)
REMINDER_NOTIFICATION_TIMEOUT_SECONDS = env_int("JARVIS_REMINDER_NOTIFICATION_TIMEOUT", 15)
HEARTBEAT_NOTIFICATION_TIMEOUT_SECONDS = env_int("JARVIS_HEARTBEAT_NOTIFICATION_TIMEOUT", 8)
EDITOR_LAUNCH_WAIT_SECONDS = env_float("JARVIS_EDITOR_LAUNCH_WAIT", 3.0)
EDITOR_COMMAND_PAUSE_SECONDS = env_float("JARVIS_EDITOR_COMMAND_PAUSE", 0.5)

# General computer-control settings keep desktop automation safety/fallback behavior tunable.
COMPUTER_CONTROL_STEP_WAIT_SECONDS = env_float("JARVIS_COMPUTER_CONTROL_STEP_WAIT", 0.5)
COMPUTER_CONTROL_APP_READY_WAIT_SECONDS = env_float("JARVIS_COMPUTER_CONTROL_APP_READY_WAIT", 1.5)
COMPUTER_CONTROL_NOTIFY_TIMEOUT_SECONDS = env_int("JARVIS_COMPUTER_CONTROL_NOTIFY_TIMEOUT", 8)
COMPUTER_CONTROL_KEY_PAUSE_SECONDS = env_float("JARVIS_COMPUTER_CONTROL_KEY_PAUSE", 0.08)
COMPUTER_CONTROL_MAX_STEP_ATTEMPTS = env_int("JARVIS_COMPUTER_CONTROL_MAX_STEP_ATTEMPTS", 4)
COMPUTER_CONTROL_WAIT_TIMEOUT_SECONDS = env_float("JARVIS_COMPUTER_CONTROL_WAIT_TIMEOUT", 6.0)
COMPUTER_CONTROL_WAIT_POLL_SECONDS = env_float("JARVIS_COMPUTER_CONTROL_WAIT_POLL", 0.25)
PAINT_DRAW_DURATION_SECONDS = env_float("JARVIS_PAINT_DRAW_DURATION", 0.2)
PAINT_CANVAS_X_RATIO = env_float("JARVIS_PAINT_CANVAS_X_RATIO", 0.5)
PAINT_CANVAS_Y_RATIO = env_float("JARVIS_PAINT_CANVAS_Y_RATIO", 0.55)
PAINT_DRAW_SIZE_PIXELS = env_int("JARVIS_PAINT_DRAW_SIZE", 160)

# GUI automation defaults are centralized because window readiness varies by machine.
GUI_CLICK_TIMEOUT_SECONDS = env_float("JARVIS_GUI_CLICK_TIMEOUT", 5.0)
GUI_TYPE_TIMEOUT_SECONDS = env_float("JARVIS_GUI_TYPE_TIMEOUT", 8.0)
GUI_FOCUS_PAUSE_SECONDS = env_float("JARVIS_GUI_FOCUS_PAUSE", 0.3)
GUI_FALLBACK_TYPE_WAIT_SECONDS = env_float("JARVIS_GUI_FALLBACK_TYPE_WAIT", 1.5)
GUI_WAIT_POLL_SECONDS = env_float("JARVIS_GUI_WAIT_POLL", 0.2)
