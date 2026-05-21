import os
import logging
import threading
import time

from config import OLLAMA_TAGS_TIMEOUT_SECONDS, OLLAMA_TAGS_URL

logger = logging.getLogger("jarvis.model_manager")

PREFERRED_MODELS = [
    "qwen3:8b",
    "qwen3:14b",
    "mistral:latest",
    "llama3.2:3b",
    "llama3.2:latest",
    "jarvis-core:latest",
]

FAST_MODEL    = os.getenv("JARVIS_MODEL", "qwen3:8b")
SUMMARY_MODEL = "qwen3:8b"
SMART_MODEL   = "qwen3:8b"
NERD_MODEL    = "qwen3:14b"
ACTION_MODEL  = os.getenv("JARVIS_ACTION_MODEL", "gemma3:4b")

_ollama_module = None


def _get_ollama():
    global _ollama_module
    if _ollama_module is None:
        try:
            import ollama as ollama_module
        except ModuleNotFoundError as exc:
            raise RuntimeError("The 'ollama' Python package is not installed.") from exc
        _ollama_module = ollama_module
    return _ollama_module


def get_available_models() -> list[str]:
    """
    Query Ollama for all currently pulled models.
    Returns list of model name strings.
    Returns empty list if Ollama is not running.
    """
    try:
        import requests

        # Ollama endpoint is configurable so non-default local hosts do not require code edits.
        response = requests.get(OLLAMA_TAGS_URL, timeout=OLLAMA_TAGS_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return [model["name"] for model in response.json().get("models", [])]
        return []
    except Exception as exc:
        # Model-list failures are logged so empty availability results are not silent.
        logger.debug("Ollama model list unavailable: %s", exc)
        return []


def get_best_available_model(preferred: list[str] | None = None) -> str:
    """
    Returns the best available model from Ollama.
    Checks preferred list first, then falls back to any available model.
    Priority order if no preference set:
      qwen3:8b, qwen3:14b, mistral:latest, llama3.2:3b - whatever is pulled
    """
    preferred = preferred or PREFERRED_MODELS
    available = get_available_models()

    if not available:
        return "qwen3:8b"

    return select_best_model(available, preferred=preferred)


def select_best_model(
    available_models: list[str],
    preferred: list[str] | None = None,
) -> str:
    """Select best available model from preference list."""
    preferred = preferred or PREFERRED_MODELS
    available_lower = [str(model).lower() for model in available_models]
    for preferred_name in preferred:
        preferred_key = preferred_name.replace(":", "").lower()
        for index, available_name in enumerate(available_lower):
            if preferred_key in available_name.replace(":", ""):
                logger.info(
                    "Selected model: %s (from preference list)",
                    available_models[index],
                )
                return available_models[index]
    return available_models[0] if available_models else "llama3.2:3b"


class ModelManager:
    def __init__(self):
        os.environ.setdefault("OLLAMA_KEEP_ALIVE", "10m")

        self.models = {
            "fast":    FAST_MODEL,
            "smart":   SMART_MODEL,
            "nerd":    NERD_MODEL,
            "summary": SUMMARY_MODEL,
            "action":  ACTION_MODEL,
            "embed":   "nomic-embed-text",
        }
        self.keep_alive = {
            FAST_MODEL:    "15m",
            SMART_MODEL:   "15m",
            SUMMARY_MODEL: "15m",
            NERD_MODEL:    "6m",
            ACTION_MODEL:  "15m",
            "nomic-embed-text": "5m",
        }
        self.startup_modes = ("fast", "action")
        self._warming_models = set()
        self._model_last_used = {}
        self._lock = threading.Lock()
        self._last_active_model = ""

    def resolve_model(self, mode_or_model: str) -> str:
        if not mode_or_model:
            return ""
        return self.models.get(mode_or_model, mode_or_model)

    def get_keep_alive(self, model_or_mode: str) -> str:
        model = self.resolve_model(model_or_mode)
        return self.keep_alive.get(model, os.environ.get("OLLAMA_KEEP_ALIVE", "10m"))

    def mark_model_used(self, model_or_mode: str):
        model = self.resolve_model(model_or_mode)
        with self._lock:
            self._model_last_used[model] = time.time()
            self._last_active_model = model

    def get_last_used(self, model_or_mode: str) -> float:
        model = self.resolve_model(model_or_mode)
        with self._lock:
            return float(self._model_last_used.get(model, 0.0))

    def get_last_active_model(self) -> str:
        with self._lock:
            return self._last_active_model

    def ollama_chat(self, model: str, messages: list[dict], *, options: dict | None = None, stream: bool = False):
        resolved_model = self.resolve_model(model)
        think = False if resolved_model.lower().startswith("qwen3") else None
        response = _get_ollama().chat(
            model=resolved_model,
            messages=messages,
            stream=stream,
            think=think,
            options=options or {},
            keep_alive=self.get_keep_alive(resolved_model),
        )
        self.mark_model_used(resolved_model)
        return response

    def _warm_model_once(self, model_or_mode: str):
        model = self.resolve_model(model_or_mode)
        try:
            self.ollama_chat(
                model,
                [
                    {"role": "system", "content": "Keep the model warm."},
                    {"role": "user", "content": "OK"},
                ],
                options={"temperature": 0, "num_predict": 1},
            )
        finally:
            with self._lock:
                self._warming_models.discard(model)

    def warm_model(self, mode_or_model: str, background: bool = False, force: bool = False) -> bool:
        model = self.resolve_model(mode_or_model)
        if not model:
            return False

        now = time.time()
        with self._lock:
            recently_used = (now - self._model_last_used.get(model, 0.0)) < 120
            if not force and (recently_used or model in self._warming_models):
                return False
            if background:
                self._warming_models.add(model)

        if background:
            thread = threading.Thread(target=self._warm_model_once, args=(model,), daemon=True)
            thread.start()
            return True

        self._warm_model_once(model)
        return True

    def warm_startup_models(self):
        for mode in self.startup_modes:
            self.warm_model(mode, background=False, force=True)

    def preload_mode_model(self, mode: str):
        if mode == "fast":
            return False
        return self.warm_model(mode, background=True)


model_manager = ModelManager()


def get_keep_alive(model: str) -> str:
    return model_manager.get_keep_alive(model)


def mark_model_used(model: str):
    model_manager.mark_model_used(model)


def get_last_used(model: str) -> float:
    return model_manager.get_last_used(model)


def get_last_active_model() -> str:
    return model_manager.get_last_active_model()


def ollama_chat(model: str, messages: list[dict], *, options: dict | None = None, stream: bool = False):
    return model_manager.ollama_chat(model, messages, options=options, stream=stream)


def warm_model(model: str, background: bool = False, force: bool = False) -> bool:
    return model_manager.warm_model(model, background=background, force=force)


def warm_startup_models():
    return model_manager.warm_startup_models()


def preload_mode_model(mode: str):
    return model_manager.preload_mode_model(mode)
