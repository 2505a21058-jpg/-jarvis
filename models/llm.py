from __future__ import annotations

from typing import Any

from model_manager import FAST_MODEL, model_manager


JARVIS_CORE_MODEL = "jarvis-core"
MODEL_ALIASES = {
    JARVIS_CORE_MODEL: FAST_MODEL,
}
DEFAULT_OPTIONS = {
    "temperature": 0.1,
    "num_predict": 180,
}


def resolve_model(model_name: str) -> str:
    return MODEL_ALIASES.get(str(model_name or "").strip(), str(model_name or "").strip())


def run_llm(
    messages: list[dict[str, Any]],
    model: str = JARVIS_CORE_MODEL,
    *,
    options: dict[str, Any] | None = None,
    stream: bool = False,
):
    resolved_model = resolve_model(model)
    merged_options = dict(DEFAULT_OPTIONS)
    if options:
        merged_options.update(options)

    try:
        return model_manager.ollama_chat(
            resolved_model,
            messages,
            options=merged_options,
            stream=stream,
        )
    except Exception as exc:
        raise RuntimeError(f"LLM call failed for {resolved_model}: {exc}") from exc


def chat(
    model: str,
    messages: list[dict[str, Any]],
    *,
    options: dict[str, Any] | None = None,
    stream: bool = False,
):
    return run_llm(messages, model=model, options=options, stream=stream)
