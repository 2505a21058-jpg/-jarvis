"""Compatibility wrapper for model manager helpers under the models package."""

from model_manager import (  # noqa: F401
    FAST_MODEL,
    NERD_MODEL,
    PREFERRED_MODELS,
    SMART_MODEL,
    SUMMARY_MODEL,
    get_available_models,
    get_best_available_model,
    get_keep_alive,
    get_last_active_model,
    get_last_used,
    mark_model_used,
    model_manager,
    ollama_chat,
    preload_mode_model,
    select_best_model,
    warm_model,
    warm_startup_models,
)
