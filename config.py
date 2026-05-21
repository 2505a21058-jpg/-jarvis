"""Central runtime configuration for Jarvis.
Re-exports from jconfig when available; falls back to env vars for backward compat."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    load_dotenv = None

try:
    from jconfig import get_config
    _cfg = get_config()
    _jconfig_loaded = True
except Exception:
    _cfg = None
    _jconfig_loaded = False


def _from_jconfig_or_env(field_path: str, env_key: str, default):
    if _jconfig_loaded and _cfg is not None:
        parts = field_path.split(".")
        val = _cfg
        for p in parts:
            val = getattr(val, p, None)
            if val is None:
                break
        if val is not None:
            return val
    return os.environ.get(env_key, default)


# Helper functions for env var reads (kept for backward compat)
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


# --- Constants (derived from jconfig when available, else env vars) ---

# Ollama / LLM endpoints
OLLAMA_BASE_URL = env_str("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_EMBEDDINGS_URL = f"{OLLAMA_BASE_URL}/api/embeddings"

# Timeouts
OLLAMA_TAGS_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_TAGS_TIMEOUT", 3.0)
READINESS_HTTP_TIMEOUT_SECONDS = env_float("JARVIS_READINESS_HTTP_TIMEOUT", 2.0)
OLLAMA_READY_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_READY_TIMEOUT", 10.0)
OLLAMA_READY_POLL_TIMEOUT_SECONDS = env_float("JARVIS_OLLAMA_READY_POLL_TIMEOUT", 1.0)
OLLAMA_READY_POLL_INTERVAL_SECONDS = env_float("JARVIS_OLLAMA_READY_POLL_INTERVAL", 0.5)

# API keys (always from env vars — never stored in yaml)
OPENWEATHER_API_KEY = env_first("OPENWEATHER_API_KEY", "JARVIS_OPENWEATHER_API_KEY")
RAPIDAPI_KEY = env_str("RAPIDAPI_KEY")
JARVIS_USER_AGENT = env_str("JARVIS_USER_AGENT", "JARVIS/1.0 (personal project)")
REQUEST_TIMEOUT_SECONDS = env_float("JARVIS_REQUEST_TIMEOUT", 10.0)

# Vision
VISION_MODEL = _from_jconfig_or_env("llm.vision_model", "JARVIS_VISION_MODEL", "llava")
VISION_REQUEST_TIMEOUT_SECONDS = _from_jconfig_or_env("vision.request_timeout_seconds", "JARVIS_VISION_TIMEOUT", 15.0)
SCREENSHOT_MAX_WIDTH = int(_from_jconfig_or_env("vision.screenshot_max_width", "JARVIS_SCREENSHOT_MAX_WIDTH", 1024))

# Embedding
EMBED_MODEL = _from_jconfig_or_env("llm.embed_model", "JARVIS_EMBED_MODEL", "nomic-embed-text")
EMBED_TIMEOUT_SECONDS = _from_jconfig_or_env("embedding.timeout_seconds", "JARVIS_EMBED_TIMEOUT", 5.0)
EMBED_MAX_ENTRIES = int(_from_jconfig_or_env("embedding.max_entries", "JARVIS_EMBED_MAX_ENTRIES", 1000))
EMBED_INPUT_MAX_CHARS = int(_from_jconfig_or_env("embedding.input_max_chars", "JARVIS_EMBED_INPUT_MAX_CHARS", 512))

# First-result automation
FIRST_RESULT_WAIT_SECONDS = _from_jconfig_or_env("search_result.wait_seconds", "JARVIS_FIRST_RESULT_WAIT_SECONDS", 3.0)
FIRST_RESULT_CLICK_X_RATIO = _from_jconfig_or_env("search_result.click_x_ratio", "JARVIS_FIRST_RESULT_CLICK_X_RATIO", 0.4)
FIRST_RESULT_CLICK_Y_RATIO = _from_jconfig_or_env("search_result.click_y_ratio", "JARVIS_FIRST_RESULT_CLICK_Y_RATIO", 0.35)

# Notification / SMTP / Editor
SMTP_TIMEOUT_SECONDS = _from_jconfig_or_env("smtp.timeout_seconds", "JARVIS_SMTP_TIMEOUT", 10.0)
MONITOR_NOTIFICATION_TIMEOUT_SECONDS = int(_from_jconfig_or_env("notification.monitor_timeout_seconds", "JARVIS_MONITOR_NOTIFICATION_TIMEOUT", 10))
REMINDER_NOTIFICATION_TIMEOUT_SECONDS = int(_from_jconfig_or_env("notification.reminder_timeout_seconds", "JARVIS_REMINDER_NOTIFICATION_TIMEOUT", 15))
HEARTBEAT_NOTIFICATION_TIMEOUT_SECONDS = int(_from_jconfig_or_env("notification.heartbeat_timeout_seconds", "JARVIS_HEARTBEAT_NOTIFICATION_TIMEOUT", 8))
EDITOR_LAUNCH_WAIT_SECONDS = _from_jconfig_or_env("editor.launch_wait_seconds", "JARVIS_EDITOR_LAUNCH_WAIT", 3.0)
EDITOR_COMMAND_PAUSE_SECONDS = _from_jconfig_or_env("editor.command_pause_seconds", "JARVIS_EDITOR_COMMAND_PAUSE", 0.5)

# Computer control
COMPUTER_CONTROL_STEP_WAIT_SECONDS = _from_jconfig_or_env("computer_control.step_wait_seconds", "JARVIS_COMPUTER_CONTROL_STEP_WAIT", 0.5)
COMPUTER_CONTROL_APP_READY_WAIT_SECONDS = _from_jconfig_or_env("computer_control.app_ready_wait_seconds", "JARVIS_COMPUTER_CONTROL_APP_READY_WAIT", 1.5)
COMPUTER_CONTROL_NOTIFY_TIMEOUT_SECONDS = int(_from_jconfig_or_env("computer_control.notify_timeout_seconds", "JARVIS_COMPUTER_CONTROL_NOTIFY_TIMEOUT", 8))
COMPUTER_CONTROL_KEY_PAUSE_SECONDS = _from_jconfig_or_env("computer_control.key_pause_seconds", "JARVIS_COMPUTER_CONTROL_KEY_PAUSE", 0.08)
COMPUTER_CONTROL_MAX_STEP_ATTEMPTS = int(_from_jconfig_or_env("computer_control.max_step_attempts", "JARVIS_COMPUTER_CONTROL_MAX_STEP_ATTEMPTS", 4))
COMPUTER_CONTROL_WAIT_TIMEOUT_SECONDS = _from_jconfig_or_env("computer_control.wait_timeout_seconds", "JARVIS_COMPUTER_CONTROL_WAIT_TIMEOUT", 6.0)
COMPUTER_CONTROL_WAIT_POLL_SECONDS = _from_jconfig_or_env("computer_control.wait_poll_seconds", "JARVIS_COMPUTER_CONTROL_WAIT_POLL", 0.25)

# Paint
PAINT_DRAW_DURATION_SECONDS = _from_jconfig_or_env("paint.draw_duration_seconds", "JARVIS_PAINT_DRAW_DURATION", 0.2)
PAINT_CANVAS_X_RATIO = _from_jconfig_or_env("paint.canvas_x_ratio", "JARVIS_PAINT_CANVAS_X_RATIO", 0.5)
PAINT_CANVAS_Y_RATIO = _from_jconfig_or_env("paint.canvas_y_ratio", "JARVIS_PAINT_CANVAS_Y_RATIO", 0.55)
PAINT_DRAW_SIZE_PIXELS = int(_from_jconfig_or_env("paint.draw_size_pixels", "JARVIS_PAINT_DRAW_SIZE", 160))

# GUI automation
GUI_CLICK_TIMEOUT_SECONDS = _from_jconfig_or_env("gui_automation.click_timeout_seconds", "JARVIS_GUI_CLICK_TIMEOUT", 5.0)
GUI_TYPE_TIMEOUT_SECONDS = _from_jconfig_or_env("gui_automation.type_timeout_seconds", "JARVIS_GUI_TYPE_TIMEOUT", 8.0)
GUI_FOCUS_PAUSE_SECONDS = _from_jconfig_or_env("gui_automation.focus_pause_seconds", "JARVIS_GUI_FOCUS_PAUSE", 0.3)
GUI_FALLBACK_TYPE_WAIT_SECONDS = _from_jconfig_or_env("gui_automation.fallback_type_wait_seconds", "JARVIS_GUI_FALLBACK_TYPE_WAIT", 1.5)
GUI_WAIT_POLL_SECONDS = _from_jconfig_or_env("gui_automation.wait_poll_seconds", "JARVIS_GUI_WAIT_POLL", 0.2)
