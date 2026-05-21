"""
models/llm.py

Centralized LLM access layer for Jarvis.
ALL LLM calls must go through this module.

Features:
- call_llm()         - standard completion
- call_llm_cached()  - in-process LRU-cached completion
- call_llm_json()    - completion with JSON parse and retry
- Timeout enforcement and retry with exponential backoff
- Prompt template registry and lightweight token budget logging
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import lru_cache
from typing import Any, Optional

from model_manager import model_manager


logger = logging.getLogger("jarvis.llm")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


_DEFAULT_TIMEOUT = _env_int("JARVIS_LLM_TIMEOUT", 30)
_MAX_RETRIES = 2
_PROMPT_CACHE: dict[str, str] = {}


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


def estimate_token_count(*parts: str) -> int:
    """
    Cheap token estimate for budgeting/logging.
    This is intentionally approximate so the central layer stays backend-agnostic.
    """
    text = "\n".join(str(part or "") for part in parts)
    if not text.strip():
        return 0
    return max(1, len(text) // 4)


def _effective_timeout(timeout: float | None) -> float:
    try:
        requested = float(timeout if timeout is not None else _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        requested = float(_DEFAULT_TIMEOUT)
    return max(requested, 1.0)


def _run_with_timeout(fn, timeout_seconds: float):
    """
    Enforce a caller-visible timeout on blocking model SDK calls.
    The worker thread may finish later, but Jarvis regains control immediately.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"LLM call timed out after {timeout_seconds:.1f}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _retry_delay(attempt: int) -> float:
    return 0.5 * (2 ** max(attempt, 0))


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
        from models.model_manager import PREFERRED_MODELS, get_best_available_model

        return get_best_available_model(PREFERRED_MODELS)
    except Exception as exc:
        # Model auto-detection failures are logged before falling back to the startup default.
        logger.debug("Best model detection failed: %s", exc)
        return os.getenv("JARVIS_MODEL", "qwen3:8b")


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
    "num_gpu": 1,
    "num_ctx": 8192,
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
    timeout: float = _DEFAULT_TIMEOUT,
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
    timeout: float = _DEFAULT_TIMEOUT,
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
    timeout: float = _DEFAULT_TIMEOUT,
    num_predict: int | None = None,
) -> str:
    token_budget = int(num_predict if num_predict is not None else max_tokens)
    timeout_seconds = _effective_timeout(timeout)
    input_tokens = estimate_token_count(system, user)
    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        start = time.monotonic()
        try:
            response = _run_with_timeout(
                lambda: _call_ollama(
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=token_budget,
                    model=model or JARVIS_CORE_MODEL,
                    timeout=timeout_seconds,
                ),
                timeout_seconds=timeout_seconds,
            )
            elapsed = (time.monotonic() - start) * 1000
            logger.info(
                "LLM call completed in %.0fms (input_tokens~%s, max_tokens=%s, attempt=%s)",
                elapsed,
                input_tokens,
                token_budget,
                attempt + 1,
            )
            return response
        except Exception as exc:
            last_error = exc
            logger.warning("LLM call attempt %s/%s failed: %s", attempt + 1, _MAX_RETRIES + 1, exc)
            if attempt < _MAX_RETRIES:
                time.sleep(_retry_delay(attempt))

    logger.error("LLM call failed after retries: %s", last_error)
    raise RuntimeError(f"LLM unavailable: {last_error}") from last_error


@lru_cache(maxsize=256)
def _cached_completion(
    system_key: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Inner cached completion. Cache key is the full argument tuple."""
    _ = system_key
    return call_llm(
        system=system,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm_cached(
    system_key: str,
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> str:
    """
    LRU-cached LLM call keyed by prompt type and exact prompt content.

    Use for classifiers and repeated deterministic prompts. Avoid for calls that
    depend on mutable memory, live state, or creative generation.
    """
    resolved_system = load_prompt_template(system_key, system)
    before = _cached_completion.cache_info()
    result = _cached_completion(system_key, resolved_system, user, float(temperature), int(max_tokens))
    after = _cached_completion.cache_info()
    logger.debug("LLM completion cache [%s]: before=%s after=%s", system_key, before, after)
    return result


def _clean_json_response(raw: str) -> str:
    cleaned = str(raw or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    cleaned = cleaned.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return cleaned[start:end + 1]
    return cleaned


def call_llm_json(
    system: str,
    user: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    retries: int = 2,
) -> Optional[dict]:
    """
    Call the LLM and parse a JSON object from its response.
    Returns None after retry exhaustion instead of raising parse errors.
    """
    attempts = max(int(retries or 0), 0) + 1
    retry_user = user
    for attempt in range(attempts):
        try:
            raw = call_llm(
                system=system,
                user=retry_user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            parsed = json.loads(_clean_json_response(raw))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed (attempt %s/%s): %s", attempt + 1, attempts, exc)
            if attempt < attempts - 1:
                retry_user = (
                    f"{user}\n\nThe previous response was not valid JSON. "
                    "Return only one valid JSON object, with no markdown."
                )
                time.sleep(_retry_delay(attempt))
        except Exception as exc:
            logger.warning("call_llm_json attempt %s/%s failed: %s", attempt + 1, attempts, exc)
            if attempt < attempts - 1:
                time.sleep(_retry_delay(attempt))

    logger.error("call_llm_json: all retries exhausted")
    return None


def load_prompt_template(name: str, fallback: str = "") -> str:
    """
    Load prompts/{name}.txt if present; otherwise return the inline fallback.
    Results are cached in memory so prompt file reads are cheap.
    """
    key = str(name or "").strip()
    if key in _PROMPT_CACHE:
        return _PROMPT_CACHE[key]

    path = os.path.join("prompts", f"{key}.txt")
    if key and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as prompt_file:
                template = prompt_file.read()
            _PROMPT_CACHE[key] = template
            logger.debug("Loaded prompt template: %s", key)
            return template
        except OSError as exc:
            logger.warning("Could not load prompt template %s: %s", key, exc)

    _PROMPT_CACHE[key] = fallback
    return fallback


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
    except json.JSONDecodeError as exc:
        logger.debug("Fast-chat JSON parse failed, trying embedded JSON: %s", exc)

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
