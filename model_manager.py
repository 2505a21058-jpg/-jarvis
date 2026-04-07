import os
import threading
import time

import ollama

FAST_MODEL = "llama3.2:3b"
SUMMARY_MODEL = "phi3:mini"
SMART_MODEL = "qwen3:8b"
NERD_MODEL = "qwen3:14b"

MODEL_KEEP_ALIVE = {
    FAST_MODEL: "15m",
    SUMMARY_MODEL: "10m",
    SMART_MODEL: "8m",
    NERD_MODEL: "6m",
}

MODE_MODEL_MAP = {
    "fast": FAST_MODEL,
    "smart": SMART_MODEL,
    "nerd": NERD_MODEL,
}

STARTUP_WARM_MODELS = (FAST_MODEL, SUMMARY_MODEL)
_warming_models = set()
_model_last_used = {}
_model_lock = threading.Lock()
_last_active_model = ""

os.environ.setdefault("OLLAMA_KEEP_ALIVE", "10m")


def get_keep_alive(model: str) -> str:
    return MODEL_KEEP_ALIVE.get(model, os.environ.get("OLLAMA_KEEP_ALIVE", "10m"))


def mark_model_used(model: str):
    global _last_active_model
    with _model_lock:
        _model_last_used[model] = time.time()
        _last_active_model = model


def get_last_used(model: str) -> float:
    with _model_lock:
        return float(_model_last_used.get(model, 0.0))


def get_last_active_model() -> str:
    with _model_lock:
        return _last_active_model


def ollama_chat(model: str, messages: list[dict], *, options: dict | None = None, stream: bool = False):
    keep_alive = get_keep_alive(model)
    response = ollama.chat(
        model=model,
        messages=messages,
        stream=stream,
        options=options or {},
        keep_alive=keep_alive,
    )
    mark_model_used(model)
    return response


def _warm_model_once(model: str):
    try:
        ollama_chat(
            model,
            [
                {"role": "system", "content": "Keep the model warm."},
                {"role": "user", "content": "OK"}
            ],
            options={"temperature": 0, "num_predict": 1},
        )
    finally:
        with _model_lock:
            _warming_models.discard(model)


def warm_model(model: str, background: bool = False, force: bool = False) -> bool:
    now = time.time()
    with _model_lock:
        recently_used = (now - _model_last_used.get(model, 0.0)) < 120
        if not force and (recently_used or model in _warming_models):
            return False
        if background:
            _warming_models.add(model)

    if background:
        thread = threading.Thread(target=_warm_model_once, args=(model,), daemon=True)
        thread.start()
        return True

    _warm_model_once(model)
    return True


def warm_startup_models():
    for model in STARTUP_WARM_MODELS:
        warm_model(model, background=(model != FAST_MODEL), force=True)


def preload_mode_model(mode: str):
    model = MODE_MODEL_MAP.get(mode)
    if not model or model == FAST_MODEL:
        return False
    return warm_model(model, background=True)
