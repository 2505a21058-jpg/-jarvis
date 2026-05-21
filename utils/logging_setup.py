"""
utils/logging_setup.py

Centralized logging configuration for Jarvis.
Call setup_logging() once at startup in jarvis.py.

Log format:
- Console: human-readable with color (if supported)
- File (jarvis.log): JSON lines for post-hoc analysis
"""

import json
import logging
import os
import sys
from datetime import datetime


_JARVIS_HANDLER_ATTR = "_jarvis_logging_handler"


class _JsonFormatter(logging.Formatter):
    """JSON line formatter for file logging."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "module": record.module,
                "line": record.lineno,
            }
        )


class _ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for console."""

    GREY = "\x1b[38;5;246m"
    RESET = "\x1b[0m"
    USE_COLOR = sys.stderr.isatty()

    LEVEL_COLORS = {
        "DEBUG": "\x1b[38;5;246m",
        "INFO": "\x1b[36m",
        "WARNING": "\x1b[33m",
        "ERROR": "\x1b[31m",
        "CRITICAL": "\x1b[1;31m",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        level = record.levelname
        msg = record.getMessage()

        if self.USE_COLOR:
            color = self.LEVEL_COLORS.get(level, "")
            return (
                f"{self.GREY}{ts}{self.RESET} "
                f"{color}{level:<8}{self.RESET} "
                f"{self.GREY}{record.name:<24}{self.RESET} {msg}"
            )
        return f"{ts} {level:<8} {record.name:<24} {msg}"


def _remove_existing_jarvis_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if getattr(handler, _JARVIS_HANDLER_ATTR, False):
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass


def setup_logging(
    console_level: str = None,
    log_file: str = "jarvis.log",
    file_level: str = "DEBUG",
) -> None:
    """
    Initialize Jarvis logging.
    Call once at startup.

    console_level: overrides JARVIS_LOG_LEVEL env var (default INFO)
    log_file: path to JSON log file
    """
    console_level = console_level or os.getenv("JARVIS_LOG_LEVEL", "INFO")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    _remove_existing_jarvis_handlers(root)

    ch = logging.StreamHandler(sys.stderr)
    setattr(ch, _JARVIS_HANDLER_ATTR, True)
    ch.setLevel(getattr(logging, console_level.upper(), logging.INFO))
    ch.setFormatter(_ConsoleFormatter())
    root.addHandler(ch)

    if log_file:
        try:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            setattr(fh, _JARVIS_HANDLER_ATTR, True)
            fh.setLevel(getattr(logging, file_level.upper(), logging.DEBUG))
            fh.setFormatter(_JsonFormatter())
            root.addHandler(fh)
        except OSError as e:
            logging.warning("Could not open log file %s: %s", log_file, e)

    for noisy in ["urllib3", "httpx", "httpcore", "openai", "anthropic"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("jarvis").info(
        "Logging initialized | console=%s | file=%s",
        console_level,
        log_file,
    )
