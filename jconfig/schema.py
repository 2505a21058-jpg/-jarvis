from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class LLMConfig:
    main_model: str = "llama3.2:3b"
    fast_model: str = "gemma3"
    embed_model: str = "nomic-embed-text"
    vision_model: str = "llava"
    ollama_host: str = "http://localhost:11434"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 1024


@dataclass
class VisionConfig:
    model: str = "llava"
    request_timeout_seconds: float = 15.0
    screenshot_max_width: int = 1024


@dataclass
class EmbeddingConfig:
    model: str = "nomic-embed-text"
    timeout_seconds: float = 5.0
    max_entries: int = 1000
    input_max_chars: int = 512


@dataclass
class MemoryConfig:
    recent_max_entries: int = 200
    long_term_max_entries: int = 2000
    experience_max_entries: int = 500
    promotion_importance_threshold: float = 0.85
    prune_experiences_at_mb: float = 5.0
    promotion_sweep_interval_hours: float = 8.0
    semantic_similarity_threshold: float = 0.3
    context_budget_tokens: int = 1200


@dataclass
class ExecutorConfig:
    max_retries: int = 3
    base_delay_ms: float = 200.0
    backoff_factor: float = 2.0
    default_skill_timeout_seconds: float = 10.0
    thread_pool_max_workers: int = 4
    vision_verify_enabled: bool = False
    permission_policy: str = "allow_all"


@dataclass
class GUIAutomationConfig:
    click_timeout_seconds: float = 5.0
    type_timeout_seconds: float = 8.0
    focus_pause_seconds: float = 0.3
    fallback_type_wait_seconds: float = 1.5
    wait_poll_seconds: float = 0.2


@dataclass
class ComputerControlConfig:
    step_wait_seconds: float = 0.5
    app_ready_wait_seconds: float = 1.5
    notify_timeout_seconds: int = 8
    key_pause_seconds: float = 0.08
    max_step_attempts: int = 4
    wait_timeout_seconds: float = 6.0
    wait_poll_seconds: float = 0.25


@dataclass
class PaintConfig:
    draw_duration_seconds: float = 0.2
    canvas_x_ratio: float = 0.5
    canvas_y_ratio: float = 0.55
    draw_size_pixels: int = 160


@dataclass
class SearchResultConfig:
    wait_seconds: float = 3.0
    click_x_ratio: float = 0.4
    click_y_ratio: float = 0.35


@dataclass
class NetworkConfig:
    request_timeout_seconds: float = 10.0
    ollama_tags_timeout_seconds: float = 3.0
    readiness_http_timeout_seconds: float = 2.0
    ollama_ready_timeout_seconds: float = 10.0
    ollama_ready_poll_timeout_seconds: float = 1.0
    ollama_ready_poll_interval_seconds: float = 0.5


@dataclass
class SMTPConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    timeout_seconds: float = 10.0


@dataclass
class NotificationConfig:
    monitor_timeout_seconds: int = 10
    reminder_timeout_seconds: int = 15
    heartbeat_timeout_seconds: int = 8


@dataclass
class EditorConfig:
    launch_wait_seconds: float = 3.0
    command_pause_seconds: float = 0.5


@dataclass
class RemoteConfig:
    enabled: bool = False
    bridge_token: str = ""
    telegram_bot_token: str = ""
    websocket_host: str = "127.0.0.1"
    websocket_port: int = 8765
    high_risk_skills: list = field(default_factory=lambda: [
        "delete", "format", "system_command", "send_email"
    ])


@dataclass
class HeartbeatConfig:
    enabled: bool = True
    interval_seconds: float = 600.0
    check_downloads: bool = True
    check_memory_patterns: bool = True
    check_pending_tasks: bool = True


@dataclass
class UserConfig:
    name: str = ""
    user_agent: str = "JARVIS/1.0 (personal project)"
    preferred_browser: str = "chrome"
    default_search_engine: str = "google"
    timezone: str = "UTC"


@dataclass
class LoggingConfig:
    level: LogLevel = LogLevel.INFO
    log_file: str = "jarvis.log"
    console_colors: bool = True
    json_logs: bool = True
    max_log_size_mb: float = 10.0


@dataclass
class JarvisConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    gui_automation: GUIAutomationConfig = field(default_factory=GUIAutomationConfig)
    computer_control: ComputerControlConfig = field(default_factory=ComputerControlConfig)
    paint: PaintConfig = field(default_factory=PaintConfig)
    search_result: SearchResultConfig = field(default_factory=SearchResultConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    smtp: SMTPConfig = field(default_factory=SMTPConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    editor: EditorConfig = field(default_factory=EditorConfig)
    remote: RemoteConfig = field(default_factory=RemoteConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    user: UserConfig = field(default_factory=UserConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
