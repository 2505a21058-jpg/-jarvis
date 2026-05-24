"""
interfaces/web/status.py

Probes every Jarvis component and returns a status dict.
Used by the web UI Dev Board.
"""

from __future__ import annotations
import importlib.util
import logging
import os
import time
import urllib.request
from typing import Any

logger = logging.getLogger("jarvis.web.status")


def _http_get(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


def _ollama_models() -> list[str]:
    try:
        from config import OLLAMA_TAGS_URL
        import json
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=3) as r:
            data = json.loads(r.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def probe_all(memory=None) -> dict[str, Any]:
    """Probe every component and return status tree."""
    models = _ollama_models()
    model_bases = {m.split(":")[0].lower() for m in models}
    now = time.time()

    result = {
        "timestamp": now,
        "sections": {},
    }

    # ── COMPUTE ──────────────────────────────────
    compute = {}
    for name, tag in [("qwen3:8b", "qwen3"), ("gemma3:4b", "gemma3"),
                      ("nomic-embed-text", "nomic"), ("llava", "llava")]:
        ok = tag in model_bases
        compute[name] = {"ok": ok, "detail": "pulled" if ok else "not pulled"}
    result["sections"]["compute"] = {"label": "COMPUTE", "items": compute}

    # ── BROWSER ──────────────────────────────────
    browser = {}
    browser["playwright"] = {
        "ok": importlib.util.find_spec("playwright") is not None,
        "detail": "installed" if importlib.util.find_spec("playwright") else "not installed",
    }
    browser["chrome_cdp"] = {
        "ok": _http_get("http://localhost:9222/json/version"),
        "detail": "port 9222" if _http_get("http://localhost:9222/json/version") else "not running",
    }
    result["sections"]["browser"] = {"label": "BROWSER", "items": browser}

    # ── VISION ───────────────────────────────────
    vision = {}
    try:
        from rawvision import RawVision
        t0 = time.monotonic()
        ctx = RawVision.capture()
        dt = (time.monotonic() - t0) * 1000
        vision["rawvision"] = {
            "ok": len(ctx.elements) > 0,
            "detail": f"{len(ctx.elements)} elements in {dt:.0f}ms",
        }
    except Exception as e:
        vision["rawvision"] = {"ok": False, "detail": str(e)[:60]}

    vision["mss"] = {
        "ok": importlib.util.find_spec("mss") is not None,
        "detail": "installed" if importlib.util.find_spec("mss") else "not installed",
    }
    vision["llava_vision"] = {
        "ok": "llava" in model_bases,
        "detail": "available" if "llava" in model_bases else "not pulled",
    }
    result["sections"]["vision"] = {"label": "VISION", "items": vision}

    # ── AUTOMATION (HANDS) ───────────────────────
    hands = {}
    for engine in ["terminal_engine", "uia_engine", "cdp_engine"]:
        try:
            spec = importlib.util.find_spec(f"agent.hands.engines.{engine}")
            hands[engine.replace("_engine", "")] = {
                "ok": spec is not None,
                "detail": "loaded" if spec else "not found",
            }
        except Exception:
            hands[engine.replace("_engine", "")] = {"ok": False, "detail": "error"}
    result["sections"]["automation"] = {"label": "AUTOMATION", "items": hands}

    # ── NETWORK ──────────────────────────────────
    net = {}
    net["ollama"] = {
        "ok": _http_get("http://localhost:11434/api/tags"),
        "detail": "localhost:11434",
    }
    net["websocket_bridge"] = {
        "ok": os.environ.get("JARVIS_REMOTE_BRIDGE", "").lower() == "true",
        "detail": "port 8765" if os.environ.get("JARVIS_REMOTE_BRIDGE", "").lower() == "true" else "disabled",
    }
    net["telegram"] = {
        "ok": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "detail": "token set" if os.environ.get("TELEGRAM_BOT_TOKEN") else "no token",
    }
    result["sections"]["network"] = {"label": "NETWORK", "items": net}

    # ── MEMORY ───────────────────────────────────
    mem = {}
    if memory is not None:
        try:
            mem["semantic"] = {
                "ok": memory.is_semantic_available(),
                "detail": "active" if memory.is_semantic_available() else "offline",
            }
            entries = len(getattr(memory._experience_index, "_entries", ()))
            mem["entries"] = {
                "ok": entries > 0,
                "detail": f"{entries:,} indexed",
            }
        except Exception as e:
            mem["semantic"] = {"ok": False, "detail": str(e)[:60]}
    else:
        mem["semantic"] = {"ok": False, "detail": "memory not initialized"}
        mem["entries"] = {"ok": False, "detail": "unknown"}
    result["sections"]["memory"] = {"label": "MEMORY", "items": mem}

    # ── SYSTEM ───────────────────────────────────
    sys_info = {}
    import platform, psutil
    sys_info["platform"] = {"ok": True, "detail": f"{platform.system()} {platform.release()}"}
    sys_info["cpu"] = {"ok": True, "detail": f"{psutil.cpu_count()} cores"}
    mem_virt = psutil.virtual_memory()
    sys_info["ram"] = {
        "ok": mem_virt.percent < 90,
        "detail": f"{mem_virt.used // (1024**3)}GB / {mem_virt.total // (1024**3)}GB ({mem_virt.percent}%)",
    }
    result["sections"]["system"] = {"label": "SYSTEM", "items": sys_info}

    return result
