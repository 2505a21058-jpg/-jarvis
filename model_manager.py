import os
import threading
import time

FAST_MODEL = "llama3.2:3b"
SUMMARY_MODEL = "phi3:mini"
SMART_MODEL = "qwen3:8b"
NERD_MODEL = "qwen3:14b"

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

        response = requests.get("http://localhost:11434/api/tags", timeout=3.0)
        if response.status_code == 200:
            return [model["name"] for model in response.json().get("models", [])]
        return []
    except Exception:
        return []


def get_best_available_model(preferred: list[str] | None = None) -> str:
    """
    Returns the best available model from Ollama.
    Checks preferred list first, then falls back to any available model.
    Priority order if no preference set:
      llama3.2:3b, llama3, mistral, phi3, gemma, qwen - whatever is pulled
    """
    default_priority = [
        "llama3.2:3b",
        "llama3.2",
        "llama3:8b",
        "llama3",
        "mistral",
        "phi3",
        "gemma",
        "qwen2",
        "deepseek",
    ]
    preferred = preferred or default_priority
    available = get_available_models()

    if not available:
        return "mistral"

    for preferred_name in preferred:
        for available_name in available:
            if preferred_name in available_name:
                return available_name

    return available[0]


class ModelManager:
    def __init__(self):
        os.environ.setdefault("OLLAMA_KEEP_ALIVE", "10m")

        self.models = {
            "fast": FAST_MODEL,
            "smart": SMART_MODEL,
            "nerd": NERD_MODEL,
            "summary": SUMMARY_MODEL,
        }
        self.keep_alive = {
            FAST_MODEL: "10m",
            SUMMARY_MODEL: "10m",
            SMART_MODEL: "8m",
            NERD_MODEL: "6m",
        }
        self.startup_modes = ("fast",)
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
        response = _get_ollama().chat(
            model=resolved_model,
            messages=messages,
            stream=stream,
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
