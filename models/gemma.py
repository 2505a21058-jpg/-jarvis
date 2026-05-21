"""
models/gemma.py

Gemma 3 client via Ollama local API.
Used for all PC automation and browser control tasks.
Fast, local, no API cost, no reasoning overhead.

Ollama must be running: ollama serve
Model must be pulled: ollama pull gemma3:4b
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request

logger = logging.getLogger("jarvis.gemma")

_OLLAMA_BASE = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
_GEMMA_MODEL = os.getenv(
    "JARVIS_GEMMA_MODEL",
    os.getenv("JARVIS_ACTION_MODEL", "gemma3:4b"),
)
_GEMMA_TIMEOUT = int(os.getenv("JARVIS_GEMMA_TIMEOUT", "20"))


def is_available() -> bool:
    """Check if Ollama is running and Gemma model is available."""
    try:
        req = urllib.request.Request(f"{_OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            models = [m["name"].split(":")[0] for m in data.get("models", [])]
            return _GEMMA_MODEL.split(":")[0] in models
    except Exception:
        return False


def call_gemma(
    prompt: str,
    system: str = "",
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Call Gemma via Ollama /api/generate endpoint.
    Returns text response or raises on failure.
    """
    payload = {
        "model": _GEMMA_MODEL,
        "prompt": prompt,
        "system": system
        or (
            "You are a computer automation assistant. "
            "Generate precise, executable action sequences. "
            "Return only what is asked - no explanation."
        ),
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_OLLAMA_BASE}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=_GEMMA_TIMEOUT) as resp:
            data = json.loads(resp.read())
            elapsed = (time.monotonic() - start) * 1000
            response = data.get("response", "").strip()
            logger.debug("[GEMMA] %.0fms | tokens=%s", elapsed, data.get("eval_count", "?"))
            return response
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama not reachable: {e}") from e


def call_gemma_vision(
    prompt: str,
    image_b64: str,
    system: str = "",
    temperature: float = 0.0,
    max_tokens: int = 512,
) -> str:
    """
    Call Gemma3:4b with a screenshot for visual decisions.
    image_b64 is a base64 encoded PNG/JPEG string.
    """
    payload = {
        "model": _GEMMA_MODEL,
        "prompt": prompt,
        "system": system
        or (
            "You are a computer automation agent. "
            "Look at the screenshot and decide the next action. "
            "Return only valid JSON."
        ),
        "images": [image_b64],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_OLLAMA_BASE}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=_GEMMA_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        raise ConnectionError(f"Ollama not reachable: {e}") from e


def _clean_json_response(raw: str) -> str:
    cleaned = str(raw or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    return cleaned.strip().rstrip("```").strip()


def call_gemma_json(
    prompt: str,
    system: str = "",
    retries: int = 2,
    max_tokens: int = 512,
) -> dict:
    """
    Call Gemma and parse JSON response.
    Returns dict or raises ValueError on parse failure.
    """
    json_system = (system or "") + "\nReturn ONLY valid JSON. No markdown, no backticks, no explanation."
    raw = ""

    for attempt in range(retries + 1):
        try:
            raw = call_gemma(
                prompt,
                system=json_system,
                max_tokens=max_tokens,
            )
            return json.loads(_clean_json_response(raw))
        except json.JSONDecodeError:
            if attempt < retries:
                logger.warning("[GEMMA] JSON parse failed attempt %s, retrying", attempt + 1)
            else:
                raise ValueError(f"Gemma returned non-JSON: {raw[:200]}")
        except TimeoutError:
            if attempt < retries:
                logger.warning("[GEMMA] Timed out attempt %s, retrying", attempt + 1)
            else:
                raise

    raise ValueError("Gemma returned non-JSON")


def call_gemma_vision_json(
    prompt: str,
    image_b64: str,
    system: str = "",
    retries: int = 2,
) -> dict:
    """Call Gemma3 with screenshot and parse JSON response."""
    json_system = (
        (system or "")
        + "\nReturn ONLY valid JSON. No markdown, no explanation."
    )
    raw = ""
    for attempt in range(retries + 1):
        try:
            raw = call_gemma_vision(
                prompt,
                image_b64,
                system=json_system,
            )
            return json.loads(_clean_json_response(raw))
        except json.JSONDecodeError:
            if attempt < retries:
                logger.warning(
                    "[GEMMA] Vision JSON parse failed attempt %s",
                    attempt + 1,
                )
            else:
                raise ValueError(
                    f"Gemma vision returned non-JSON: {raw[:200]}"
                )
    raise ValueError("Gemma vision returned non-JSON")
