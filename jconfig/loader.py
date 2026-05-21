import os
import logging
from typing import Optional
from jconfig.schema import (
    JarvisConfig,
    LLMConfig,
    VisionConfig,
    EmbeddingConfig,
    MemoryConfig,
    ExecutorConfig,
    GUIAutomationConfig,
    ComputerControlConfig,
    PaintConfig,
    SearchResultConfig,
    NetworkConfig,
    SMTPConfig,
    NotificationConfig,
    EditorConfig,
    RemoteConfig,
    HeartbeatConfig,
    UserConfig,
    LoggingConfig,
    LogLevel,
)

logger = logging.getLogger("jarvis.config")

_config: Optional[JarvisConfig] = None
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "jconfig.yaml")


def _load_yaml(path: str) -> dict:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except ImportError:
        logger.warning("PyYAML not installed. Run: pip install pyyaml")
        return {}
    except Exception as e:
        logger.error(f"Failed to load jconfig.yaml: {e}")
        return {}


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


_ENV_MAP = {
    "JARVIS_MODEL": ("llm", "main_model"),
    "JARVIS_FAST_MODEL": ("llm", "fast_model"),
    "JARVIS_ACTION_MODEL": ("llm", "fast_model"),
    "JARVIS_EMBED_MODEL": ("llm", "embed_model"),
    "JARVIS_VISION_MODEL": ("llm", "vision_model"),
    "OLLAMA_HOST": ("llm", "ollama_host"),
    "JARVIS_LLM_TIMEOUT": ("llm", "timeout_seconds"),
    "JARVIS_LLM_RETRIES": ("llm", "max_retries"),
    "JARVIS_VISION_TIMEOUT": ("vision", "request_timeout_seconds"),
    "JARVIS_SCREENSHOT_MAX_WIDTH": ("vision", "screenshot_max_width"),
    "JARVIS_EMBED_TIMEOUT": ("embedding", "timeout_seconds"),
    "JARVIS_EMBED_MAX_ENTRIES": ("embedding", "max_entries"),
    "JARVIS_EMBED_INPUT_MAX_CHARS": ("embedding", "input_max_chars"),
    "JARVIS_VISION_VERIFY": ("executor", "vision_verify_enabled"),
    "JARVIS_EXECUTOR_TIMEOUT": ("executor", "default_skill_timeout_seconds"),
    "JARVIS_EXECUTOR_RETRIES": ("executor", "max_retries"),
    "JARVIS_EXECUTOR_BASE_DELAY_MS": ("executor", "base_delay_ms"),
    "JARVIS_GUI_CLICK_TIMEOUT": ("gui_automation", "click_timeout_seconds"),
    "JARVIS_GUI_TYPE_TIMEOUT": ("gui_automation", "type_timeout_seconds"),
    "JARVIS_GUI_FOCUS_PAUSE": ("gui_automation", "focus_pause_seconds"),
    "JARVIS_GUI_FALLBACK_TYPE_WAIT": ("gui_automation", "fallback_type_wait_seconds"),
    "JARVIS_GUI_WAIT_POLL": ("gui_automation", "wait_poll_seconds"),
    "JARVIS_COMPUTER_CONTROL_STEP_WAIT": ("computer_control", "step_wait_seconds"),
    "JARVIS_COMPUTER_CONTROL_APP_READY_WAIT": ("computer_control", "app_ready_wait_seconds"),
    "JARVIS_COMPUTER_CONTROL_NOTIFY_TIMEOUT": ("computer_control", "notify_timeout_seconds"),
    "JARVIS_COMPUTER_CONTROL_KEY_PAUSE": ("computer_control", "key_pause_seconds"),
    "JARVIS_COMPUTER_CONTROL_MAX_STEP_ATTEMPTS": ("computer_control", "max_step_attempts"),
    "JARVIS_COMPUTER_CONTROL_WAIT_TIMEOUT": ("computer_control", "wait_timeout_seconds"),
    "JARVIS_COMPUTER_CONTROL_WAIT_POLL": ("computer_control", "wait_poll_seconds"),
    "JARVIS_PAINT_DRAW_DURATION": ("paint", "draw_duration_seconds"),
    "JARVIS_PAINT_CANVAS_X_RATIO": ("paint", "canvas_x_ratio"),
    "JARVIS_PAINT_CANVAS_Y_RATIO": ("paint", "canvas_y_ratio"),
    "JARVIS_PAINT_DRAW_SIZE": ("paint", "draw_size_pixels"),
    "JARVIS_FIRST_RESULT_WAIT_SECONDS": ("search_result", "wait_seconds"),
    "JARVIS_FIRST_RESULT_CLICK_X_RATIO": ("search_result", "click_x_ratio"),
    "JARVIS_FIRST_RESULT_CLICK_Y_RATIO": ("search_result", "click_y_ratio"),
    "JARVIS_REQUEST_TIMEOUT": ("network", "request_timeout_seconds"),
    "JARVIS_OLLAMA_TAGS_TIMEOUT": ("network", "ollama_tags_timeout_seconds"),
    "JARVIS_READINESS_HTTP_TIMEOUT": ("network", "readiness_http_timeout_seconds"),
    "JARVIS_OLLAMA_READY_TIMEOUT": ("network", "ollama_ready_timeout_seconds"),
    "JARVIS_OLLAMA_READY_POLL_TIMEOUT": ("network", "ollama_ready_poll_timeout_seconds"),
    "JARVIS_OLLAMA_READY_POLL_INTERVAL": ("network", "ollama_ready_poll_interval_seconds"),
    "JARVIS_SMTP_TIMEOUT": ("smtp", "timeout_seconds"),
    "JARVIS_SMTP_HOST": ("smtp", "host"),
    "JARVIS_SMTP_PORT": ("smtp", "port"),
    "JARVIS_SMTP_USER": ("smtp", "user"),
    "JARVIS_SMTP_PASS": ("smtp", "password"),
    "JARVIS_MONITOR_NOTIFICATION_TIMEOUT": ("notification", "monitor_timeout_seconds"),
    "JARVIS_REMINDER_NOTIFICATION_TIMEOUT": ("notification", "reminder_timeout_seconds"),
    "JARVIS_HEARTBEAT_NOTIFICATION_TIMEOUT": ("notification", "heartbeat_timeout_seconds"),
    "JARVIS_EDITOR_LAUNCH_WAIT": ("editor", "launch_wait_seconds"),
    "JARVIS_EDITOR_COMMAND_PAUSE": ("editor", "command_pause_seconds"),
    "JARVIS_HEARTBEAT": ("heartbeat", "enabled"),
    "JARVIS_HEARTBEAT_INTERVAL": ("heartbeat", "interval_seconds"),
    "JARVIS_REMOTE_BRIDGE": ("remote", "enabled"),
    "JARVIS_BRIDGE_TOKEN": ("remote", "bridge_token"),
    "TELEGRAM_BOT_TOKEN": ("remote", "telegram_bot_token"),
    "JARVIS_USER_NAME": ("user", "name"),
    "JARVIS_USER_AGENT": ("user", "user_agent"),
    "JARVIS_LOG_LEVEL": ("logging", "level"),
    "JARVIS_JSON_LOGS": ("logging", "json_logs"),
}


def _read_yaml_section(yaml_data: dict, section: str) -> dict:
    return yaml_data.get(section) or {}


def _sync_env(config: JarvisConfig) -> None:
    os.environ.setdefault("JARVIS_MODEL", config.llm.main_model)
    os.environ.setdefault("JARVIS_ACTION_MODEL", config.llm.fast_model)
    os.environ.setdefault("JARVIS_EMBED_MODEL", config.llm.embed_model)
    os.environ.setdefault("JARVIS_VISION_MODEL", config.llm.vision_model)
    os.environ.setdefault("OLLAMA_HOST", config.llm.ollama_host)
    os.environ.setdefault("JARVIS_LLM_TIMEOUT", str(config.llm.timeout_seconds))
    os.environ.setdefault("JARVIS_LLM_RETRIES", str(config.llm.max_retries))

    os.environ.setdefault("JARVIS_VISION_TIMEOUT", str(config.vision.request_timeout_seconds))
    os.environ.setdefault("JARVIS_SCREENSHOT_MAX_WIDTH", str(config.vision.screenshot_max_width))

    os.environ.setdefault("JARVIS_EMBED_TIMEOUT", str(config.embedding.timeout_seconds))
    os.environ.setdefault("JARVIS_EMBED_MAX_ENTRIES", str(config.embedding.max_entries))
    os.environ.setdefault("JARVIS_EMBED_INPUT_MAX_CHARS", str(config.embedding.input_max_chars))

    os.environ.setdefault("JARVIS_VISION_VERIFY", str(config.executor.vision_verify_enabled).lower())
    os.environ.setdefault("JARVIS_EXECUTOR_TIMEOUT", str(config.executor.default_skill_timeout_seconds))
    os.environ.setdefault("JARVIS_EXECUTOR_RETRIES", str(config.executor.max_retries))
    os.environ.setdefault("JARVIS_EXECUTOR_BASE_DELAY_MS", str(config.executor.base_delay_ms))

    os.environ.setdefault("JARVIS_GUI_CLICK_TIMEOUT", str(config.gui_automation.click_timeout_seconds))
    os.environ.setdefault("JARVIS_GUI_TYPE_TIMEOUT", str(config.gui_automation.type_timeout_seconds))
    os.environ.setdefault("JARVIS_GUI_FOCUS_PAUSE", str(config.gui_automation.focus_pause_seconds))
    os.environ.setdefault("JARVIS_GUI_FALLBACK_TYPE_WAIT", str(config.gui_automation.fallback_type_wait_seconds))
    os.environ.setdefault("JARVIS_GUI_WAIT_POLL", str(config.gui_automation.wait_poll_seconds))

    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_STEP_WAIT", str(config.computer_control.step_wait_seconds))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_APP_READY_WAIT", str(config.computer_control.app_ready_wait_seconds))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_NOTIFY_TIMEOUT", str(config.computer_control.notify_timeout_seconds))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_KEY_PAUSE", str(config.computer_control.key_pause_seconds))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_MAX_STEP_ATTEMPTS", str(config.computer_control.max_step_attempts))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_WAIT_TIMEOUT", str(config.computer_control.wait_timeout_seconds))
    os.environ.setdefault("JARVIS_COMPUTER_CONTROL_WAIT_POLL", str(config.computer_control.wait_poll_seconds))

    os.environ.setdefault("JARVIS_PAINT_DRAW_DURATION", str(config.paint.draw_duration_seconds))
    os.environ.setdefault("JARVIS_PAINT_CANVAS_X_RATIO", str(config.paint.canvas_x_ratio))
    os.environ.setdefault("JARVIS_PAINT_CANVAS_Y_RATIO", str(config.paint.canvas_y_ratio))
    os.environ.setdefault("JARVIS_PAINT_DRAW_SIZE", str(config.paint.draw_size_pixels))

    os.environ.setdefault("JARVIS_FIRST_RESULT_WAIT_SECONDS", str(config.search_result.wait_seconds))
    os.environ.setdefault("JARVIS_FIRST_RESULT_CLICK_X_RATIO", str(config.search_result.click_x_ratio))
    os.environ.setdefault("JARVIS_FIRST_RESULT_CLICK_Y_RATIO", str(config.search_result.click_y_ratio))

    os.environ.setdefault("JARVIS_REQUEST_TIMEOUT", str(config.network.request_timeout_seconds))
    os.environ.setdefault("JARVIS_OLLAMA_TAGS_TIMEOUT", str(config.network.ollama_tags_timeout_seconds))
    os.environ.setdefault("JARVIS_READINESS_HTTP_TIMEOUT", str(config.network.readiness_http_timeout_seconds))
    os.environ.setdefault("JARVIS_OLLAMA_READY_TIMEOUT", str(config.network.ollama_ready_timeout_seconds))
    os.environ.setdefault("JARVIS_OLLAMA_READY_POLL_TIMEOUT", str(config.network.ollama_ready_poll_timeout_seconds))
    os.environ.setdefault("JARVIS_OLLAMA_READY_POLL_INTERVAL", str(config.network.ollama_ready_poll_interval_seconds))

    os.environ.setdefault("JARVIS_SMTP_TIMEOUT", str(config.smtp.timeout_seconds))
    os.environ.setdefault("JARVIS_SMTP_HOST", config.smtp.host)
    os.environ.setdefault("JARVIS_SMTP_PORT", str(config.smtp.port))
    os.environ.setdefault("JARVIS_SMTP_USER", config.smtp.user)
    os.environ.setdefault("JARVIS_SMTP_PASS", config.smtp.password)

    os.environ.setdefault("JARVIS_MONITOR_NOTIFICATION_TIMEOUT", str(config.notification.monitor_timeout_seconds))
    os.environ.setdefault("JARVIS_REMINDER_NOTIFICATION_TIMEOUT", str(config.notification.reminder_timeout_seconds))
    os.environ.setdefault("JARVIS_HEARTBEAT_NOTIFICATION_TIMEOUT", str(config.notification.heartbeat_timeout_seconds))

    os.environ.setdefault("JARVIS_EDITOR_LAUNCH_WAIT", str(config.editor.launch_wait_seconds))
    os.environ.setdefault("JARVIS_EDITOR_COMMAND_PAUSE", str(config.editor.command_pause_seconds))

    os.environ.setdefault("JARVIS_HEARTBEAT", str(config.heartbeat.enabled).lower())
    os.environ.setdefault("JARVIS_HEARTBEAT_INTERVAL", str(config.heartbeat.interval_seconds))

    os.environ.setdefault("JARVIS_REMOTE_BRIDGE", str(config.remote.enabled).lower())

    os.environ.setdefault("JARVIS_USER_AGENT", config.user.user_agent)
    os.environ.setdefault("JARVIS_LOG_LEVEL", config.logging.level.value if isinstance(config.logging.level, LogLevel) else config.logging.level)
    os.environ.setdefault("JARVIS_JSON_LOGS", str(config.logging.json_logs).lower())


def load_config(config_path: str = None) -> JarvisConfig:
    yaml_data = _load_yaml(config_path or CONFIG_PATH)

    def ys(section: str) -> dict:
        return _read_yaml_section(yaml_data, section)

    config = JarvisConfig(
        llm=LLMConfig(
            main_model=_env("JARVIS_MODEL") or ys("llm").get("main_model", "llama3.2:3b"),
            fast_model=_env("JARVIS_FAST_MODEL") or ys("llm").get("fast_model", "gemma3"),
            embed_model=_env("JARVIS_EMBED_MODEL") or ys("llm").get("embed_model", "nomic-embed-text"),
            vision_model=_env("JARVIS_VISION_MODEL") or ys("llm").get("vision_model", "llava"),
            ollama_host=_env("OLLAMA_HOST") or ys("llm").get("ollama_host", "http://localhost:11434"),
            timeout_seconds=_env_float("JARVIS_LLM_TIMEOUT", ys("llm").get("timeout_seconds", 30.0)),
            max_retries=_env_int("JARVIS_LLM_RETRIES", ys("llm").get("max_retries", 3)),
        ),
        vision=VisionConfig(
            request_timeout_seconds=_env_float("JARVIS_VISION_TIMEOUT", ys("vision").get("request_timeout_seconds", 15.0)),
            screenshot_max_width=_env_int("JARVIS_SCREENSHOT_MAX_WIDTH", ys("vision").get("screenshot_max_width", 1024)),
        ),
        embedding=EmbeddingConfig(
            timeout_seconds=_env_float("JARVIS_EMBED_TIMEOUT", ys("embedding").get("timeout_seconds", 5.0)),
            max_entries=_env_int("JARVIS_EMBED_MAX_ENTRIES", ys("embedding").get("max_entries", 1000)),
            input_max_chars=_env_int("JARVIS_EMBED_INPUT_MAX_CHARS", ys("embedding").get("input_max_chars", 512)),
        ),
        memory=MemoryConfig(
            promotion_importance_threshold=float(ys("memory").get("promotion_importance_threshold", 0.85)),
            context_budget_tokens=int(ys("memory").get("context_budget_tokens", 1200)),
            recent_max_entries=int(ys("memory").get("recent_max_entries", 200)),
            long_term_max_entries=int(ys("memory").get("long_term_max_entries", 2000)),
            experience_max_entries=int(ys("memory").get("experience_max_entries", 500)),
            prune_experiences_at_mb=float(ys("memory").get("prune_experiences_at_mb", 5.0)),
            promotion_sweep_interval_hours=float(ys("memory").get("promotion_sweep_interval_hours", 8.0)),
            semantic_similarity_threshold=float(ys("memory").get("semantic_similarity_threshold", 0.3)),
        ),
        executor=ExecutorConfig(
            vision_verify_enabled=_env_bool("JARVIS_VISION_VERIFY", ys("executor").get("vision_verify_enabled", False)),
            max_retries=_env_int("JARVIS_EXECUTOR_RETRIES", ys("executor").get("max_retries", 3)),
            default_skill_timeout_seconds=_env_float("JARVIS_EXECUTOR_TIMEOUT", ys("executor").get("default_skill_timeout_seconds", 10.0)),
            base_delay_ms=_env_float("JARVIS_EXECUTOR_BASE_DELAY_MS", ys("executor").get("base_delay_ms", 200.0)),
            backoff_factor=_env_float("JARVIS_EXECUTOR_BACKOFF", ys("executor").get("backoff_factor", 2.0)),
            thread_pool_max_workers=_env_int("JARVIS_EXECUTOR_WORKERS", ys("executor").get("thread_pool_max_workers", 4)),
        ),
        gui_automation=GUIAutomationConfig(
            click_timeout_seconds=_env_float("JARVIS_GUI_CLICK_TIMEOUT", ys("gui_automation").get("click_timeout_seconds", 5.0)),
            type_timeout_seconds=_env_float("JARVIS_GUI_TYPE_TIMEOUT", ys("gui_automation").get("type_timeout_seconds", 8.0)),
            focus_pause_seconds=_env_float("JARVIS_GUI_FOCUS_PAUSE", ys("gui_automation").get("focus_pause_seconds", 0.3)),
            fallback_type_wait_seconds=_env_float("JARVIS_GUI_FALLBACK_TYPE_WAIT", ys("gui_automation").get("fallback_type_wait_seconds", 1.5)),
            wait_poll_seconds=_env_float("JARVIS_GUI_WAIT_POLL", ys("gui_automation").get("wait_poll_seconds", 0.2)),
        ),
        computer_control=ComputerControlConfig(
            step_wait_seconds=_env_float("JARVIS_COMPUTER_CONTROL_STEP_WAIT", ys("computer_control").get("step_wait_seconds", 0.5)),
            app_ready_wait_seconds=_env_float("JARVIS_COMPUTER_CONTROL_APP_READY_WAIT", ys("computer_control").get("app_ready_wait_seconds", 1.5)),
            notify_timeout_seconds=_env_int("JARVIS_COMPUTER_CONTROL_NOTIFY_TIMEOUT", ys("computer_control").get("notify_timeout_seconds", 8)),
            key_pause_seconds=_env_float("JARVIS_COMPUTER_CONTROL_KEY_PAUSE", ys("computer_control").get("key_pause_seconds", 0.08)),
            max_step_attempts=_env_int("JARVIS_COMPUTER_CONTROL_MAX_STEP_ATTEMPTS", ys("computer_control").get("max_step_attempts", 4)),
            wait_timeout_seconds=_env_float("JARVIS_COMPUTER_CONTROL_WAIT_TIMEOUT", ys("computer_control").get("wait_timeout_seconds", 6.0)),
            wait_poll_seconds=_env_float("JARVIS_COMPUTER_CONTROL_WAIT_POLL", ys("computer_control").get("wait_poll_seconds", 0.25)),
        ),
        paint=PaintConfig(
            draw_duration_seconds=_env_float("JARVIS_PAINT_DRAW_DURATION", ys("paint").get("draw_duration_seconds", 0.2)),
            canvas_x_ratio=_env_float("JARVIS_PAINT_CANVAS_X_RATIO", ys("paint").get("canvas_x_ratio", 0.5)),
            canvas_y_ratio=_env_float("JARVIS_PAINT_CANVAS_Y_RATIO", ys("paint").get("canvas_y_ratio", 0.55)),
            draw_size_pixels=_env_int("JARVIS_PAINT_DRAW_SIZE", ys("paint").get("draw_size_pixels", 160)),
        ),
        search_result=SearchResultConfig(
            wait_seconds=_env_float("JARVIS_FIRST_RESULT_WAIT", ys("search_result").get("wait_seconds", 3.0)),
            click_x_ratio=_env_float("JARVIS_FIRST_RESULT_CLICK_X_RATIO", ys("search_result").get("click_x_ratio", 0.4)),
            click_y_ratio=_env_float("JARVIS_FIRST_RESULT_CLICK_Y_RATIO", ys("search_result").get("click_y_ratio", 0.35)),
        ),
        network=NetworkConfig(
            request_timeout_seconds=_env_float("JARVIS_REQUEST_TIMEOUT", ys("network").get("request_timeout_seconds", 10.0)),
            ollama_tags_timeout_seconds=_env_float("JARVIS_OLLAMA_TAGS_TIMEOUT", ys("network").get("ollama_tags_timeout_seconds", 3.0)),
            readiness_http_timeout_seconds=_env_float("JARVIS_READINESS_HTTP_TIMEOUT", ys("network").get("readiness_http_timeout_seconds", 2.0)),
            ollama_ready_timeout_seconds=_env_float("JARVIS_OLLAMA_READY_TIMEOUT", ys("network").get("ollama_ready_timeout_seconds", 10.0)),
            ollama_ready_poll_timeout_seconds=_env_float("JARVIS_OLLAMA_READY_POLL_TIMEOUT", ys("network").get("ollama_ready_poll_timeout_seconds", 1.0)),
            ollama_ready_poll_interval_seconds=_env_float("JARVIS_OLLAMA_READY_POLL_INTERVAL", ys("network").get("ollama_ready_poll_interval_seconds", 0.5)),
        ),
        smtp=SMTPConfig(
            host=_env("JARVIS_SMTP_HOST") or ys("smtp").get("host", ""),
            port=_env_int("JARVIS_SMTP_PORT", ys("smtp").get("port", 587)),
            user=_env("JARVIS_SMTP_USER") or ys("smtp").get("user", ""),
            password=_env("JARVIS_SMTP_PASS") or ys("smtp").get("password", ""),
            timeout_seconds=_env_float("JARVIS_SMTP_TIMEOUT", ys("smtp").get("timeout_seconds", 10.0)),
        ),
        notification=NotificationConfig(
            monitor_timeout_seconds=_env_int("JARVIS_MONITOR_NOTIFICATION_TIMEOUT", ys("notification").get("monitor_timeout_seconds", 10)),
            reminder_timeout_seconds=_env_int("JARVIS_REMINDER_NOTIFICATION_TIMEOUT", ys("notification").get("reminder_timeout_seconds", 15)),
            heartbeat_timeout_seconds=_env_int("JARVIS_HEARTBEAT_NOTIFICATION_TIMEOUT", ys("notification").get("heartbeat_timeout_seconds", 8)),
        ),
        editor=EditorConfig(
            launch_wait_seconds=_env_float("JARVIS_EDITOR_LAUNCH_WAIT", ys("editor").get("launch_wait_seconds", 3.0)),
            command_pause_seconds=_env_float("JARVIS_EDITOR_COMMAND_PAUSE", ys("editor").get("command_pause_seconds", 0.5)),
        ),
        remote=RemoteConfig(
            enabled=_env_bool("JARVIS_REMOTE_BRIDGE", ys("remote").get("enabled", False)),
            bridge_token=_env("JARVIS_BRIDGE_TOKEN") or ys("remote").get("bridge_token", ""),
            telegram_bot_token=_env("TELEGRAM_BOT_TOKEN") or ys("remote").get("telegram_bot_token", ""),
        ),
        heartbeat=HeartbeatConfig(
            enabled=_env_bool("JARVIS_HEARTBEAT", ys("heartbeat").get("enabled", True)),
            interval_seconds=_env_float("JARVIS_HEARTBEAT_INTERVAL", ys("heartbeat").get("interval_seconds", 600.0)),
        ),
        user=UserConfig(
            name=_env("JARVIS_USER_NAME") or ys("user").get("name", ""),
            user_agent=_env("JARVIS_USER_AGENT") or ys("user").get("user_agent", "JARVIS/1.0 (personal project)"),
        ),
        logging=LoggingConfig(
            level=_env("JARVIS_LOG_LEVEL") or ys("logging").get("level", "INFO"),
            json_logs=_env_bool("JARVIS_JSON_LOGS", ys("logging").get("json_logs", True)),
        ),
    )

    _validate(config)
    return config


def _validate(config: JarvisConfig) -> None:
    _sync_env(config)

    if not config.llm.main_model:
        logger.error("No main LLM model configured. Set JARVIS_MODEL or llm.main_model in jconfig.yaml")

    if config.remote.enabled and not config.remote.bridge_token:
        logger.warning(
            "Remote bridge enabled but JARVIS_BRIDGE_TOKEN not set. "
            "All remote connections will be rejected."
        )

    if config.smtp.host and not config.smtp.user:
        logger.warning("SMTP host set but JARVIS_SMTP_USER not set. Email sending will fail.")


def get_config() -> JarvisConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> JarvisConfig:
    global _config
    _config = load_config()
    logger.info("Configuration reloaded")
    return _config


def save_runtime_setting(key: str, value: str) -> None:
    os.environ[key] = value

    if "PYTEST_CURRENT_TEST" in os.environ:
        logger.debug(f"pytest detected — skipping YAML write for {key}={value}")
        return

    try:
        import yaml

        try:
            with open(CONFIG_PATH, "r") as f:
                existing = yaml.safe_load(f) or {}
        except FileNotFoundError:
            existing = {}

        if key in _ENV_MAP:
            section, field_name = _ENV_MAP[key]
            if section not in existing:
                existing[section] = {}
            typed_val = value
            if value.lower() in ("true", "false"):
                typed_val = value.lower() == "true"
            elif value.replace(".", "").isdigit():
                typed_val = float(value) if "." in value else int(value)
            existing[section][field_name] = typed_val

        with open(CONFIG_PATH, "w") as f:
            yaml.dump(existing, f, default_flow_style=False)

        logger.info(f"Saved {key}={value} to jconfig.yaml")

    except Exception as e:
        logger.debug(f"Could not persist to jconfig.yaml: {e}")

    reload_config()
