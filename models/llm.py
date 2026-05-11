from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from model_manager import model_manager


logger = logging.getLogger("jarvis.llm")


class PromptCache:
    """
    Caches finalized system prompt strings by content hash.
    Guarantees byte-identical system prompts for repeated call patterns,
    enabling Ollama's KV-cache to reuse prefix computation.
    """

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._hits = 0
        self._misses = 0

    def get_or_set(self, prompt: str) -> str:
        key = hashlib.md5(prompt.encode("utf-8")).hexdigest()
        if key in self._cache:
            self._hits += 1
            return self._cache[key]
        self._cache[key] = prompt
        self._misses += 1
        return prompt

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / max(total, 1),
            "cached_prompts": len(self._cache),
        }


_prompt_cache = PromptCache()


def get_prompt_cache() -> PromptCache:
    return _prompt_cache


_ACTIVE_MODEL: str = ""


def _get_active_model() -> str:
    """
    Get the model to use for LLM calls.
    Priority:
      1. JARVIS_MODEL environment variable if set
      2. Auto-detected best available model from Ollama
    """
    env_model = os.environ.get("JARVIS_MODEL", "").strip()
    if env_model:
        return env_model

    try:
        from models.model_manager import get_best_available_model

        return get_best_available_model()
    except Exception:
        return "mistral"


def _get_cached_model() -> str:
    global _ACTIVE_MODEL
    if not _ACTIVE_MODEL:
        _ACTIVE_MODEL = _get_active_model()
        logger.info("Active model: %s", _ACTIVE_MODEL)
    return _ACTIVE_MODEL


JARVIS_CORE_MODEL = "jarvis-core"
MODEL_ALIASES = {}
DEFAULT_OPTIONS = {
    "temperature": 0.1,
    "num_predict": 180,
}


def resolve_model(model_name: str) -> str:
    requested = str(model_name or "").strip()
    if not requested or requested == JARVIS_CORE_MODEL:
        return _get_cached_model()
    return MODEL_ALIASES.get(requested, requested)


def _call_ollama_messages(
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


def run_llm(
    messages: list[dict[str, Any]],
    model: str = JARVIS_CORE_MODEL,
    *,
    options: dict[str, Any] | None = None,
    stream: bool = False,
):
    return _call_ollama_messages(messages, model=model, options=options, stream=stream)


def chat(
    model: str,
    messages: list[dict[str, Any]],
    *,
    options: dict[str, Any] | None = None,
    stream: bool = False,
):
    return run_llm(messages, model=model, options=options, stream=stream)


def _call_ollama(
    *,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    model: str | None = None,
    timeout: float = 30.0,
) -> str:
    _ = timeout
    response = _call_ollama_messages(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model or JARVIS_CORE_MODEL,
        options={
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    )
    return str(response.get("message", {}).get("content", "")).strip()


def call_llm(
    *,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    model: str | None = None,
    timeout: float = 30.0,
    num_predict: int | None = None,
) -> str:
    system = _prompt_cache.get_or_set(system)
    return _call_llm_with_system(
        system=system,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
        timeout=timeout,
        num_predict=num_predict,
    )


def _call_llm_with_system(
    *,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    model: str | None = None,
    timeout: float = 30.0,
    num_predict: int | None = None,
) -> str:
    token_budget = int(num_predict if num_predict is not None else max_tokens)
    start = time.monotonic()
    try:
        response = _call_ollama(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=token_budget,
            model=model or JARVIS_CORE_MODEL,
            timeout=timeout,
        )
        elapsed = (time.monotonic() - start) * 1000
        logger.info("LLM call completed in %.0fms", elapsed)
        return response
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise RuntimeError(f"LLM unavailable: {exc}") from exc


def call_llm_cached(
    system_key: str,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """
    Variant of call_llm that explicitly names the system prompt by key.
    system_key: short identifier (e.g. "fast_decide", "planner", "fast_chat")
    system: the full system prompt string
    Logs cache performance per key for observability.
    """
    cached_system = _prompt_cache.get_or_set(system)
    logger.debug("LLM call [%s] cache stats: %s", system_key, _prompt_cache.stats())
    return _call_llm_with_system(
        system=cached_system,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
    )


FAST_CHAT_SYSTEM = """
You are Jarvis, a local AI assistant.
Given a user message and recent context, do two things:
1. Decide if this is a pure conversational message (no tool/app/system action needed).
2. If yes, respond directly in natural language.

Return ONLY valid JSON:
{
  "is_chat": true,
  "response": "your natural language response here"
}

OR if a tool/skill/action is needed:
{
  "is_chat": false,
  "action_type": "skill|browse|open_app|search|...",
  "action_name": "name_of_action",
  "parameters": {}
}
"""


def _extract_json_dict(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def call_llm_fast_chat(user_input: str, state_context: dict, recent_history: list[dict]) -> dict:
    """
    Single LLM call that both classifies AND responds for chat turns.
    Returns parsed dict with is_chat + response, or is_chat=False + action details.
    """
    history_text = "\n".join(
        f"{str(message.get('role', 'user')).upper()}: {str(message.get('content', '')).strip()}"
        for message in list(recent_history or [])[-6:]
        if str(message.get("content", "")).strip()
    )
    state_text = json.dumps(state_context or {}, ensure_ascii=True)
    user_block = (
        f"State context:\n{state_text}\n\n"
        f"Recent history:\n{history_text or '(none)'}\n\n"
        f"User: {user_input}"
    )
    raw = call_llm_cached(
        "fast_chat",
        FAST_CHAT_SYSTEM,
        user_block,
        temperature=0.5,
        max_tokens=240,
    )
    parsed = _extract_json_dict(raw)
    if parsed is not None:
        return parsed
    return {"is_chat": True, "response": raw.strip()}
