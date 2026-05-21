"""
tools/readiness_check.py

Startup readiness checker for Jarvis.
Runs at startup and prints a clear status summary.
Shows what is active, what needs setup, and what is optional.
Never blocks startup - informational only.
"""

import logging
import os

from config import OLLAMA_TAGS_URL, READINESS_HTTP_TIMEOUT_SECONDS


logger = logging.getLogger("jarvis.readiness")


def _check_ollama() -> tuple[bool, str]:
    try:
        import requests

        # Readiness checks share the configured Ollama endpoint to avoid localhost drift.
        response = requests.get(OLLAMA_TAGS_URL, timeout=READINESS_HTTP_TIMEOUT_SECONDS)
        if response.status_code == 200:
            models = [model["name"] for model in response.json().get("models", [])]
            return True, f"Running - {len(models)} model(s) available"
        return False, "Running but API returned unexpected status"
    except Exception as exc:
        # Readiness failures are logged while keeping startup checks informational.
        logger.debug("Ollama readiness check failed: %s", exc)
        return False, "Not running - start with: ollama serve"


def _check_model(model_name: str) -> tuple[bool, str]:
    try:
        import requests

        # Model checks use the same configurable endpoint as runtime LLM calls.
        response = requests.get(OLLAMA_TAGS_URL, timeout=READINESS_HTTP_TIMEOUT_SECONDS)
        if response.status_code == 200:
            models = [model["name"] for model in response.json().get("models", [])]
            found = any(model_name.split(":")[0] in model for model in models)
            if found:
                return True, "Available"
            return False, f"Not pulled - run: ollama pull {model_name}"
        return False, "Cannot check - Ollama not responding"
    except Exception as exc:
        # Model probe failures are logged while preserving non-blocking readiness behavior.
        logger.debug("Ollama model check failed: %s", exc)
        return False, "Cannot check - Ollama not running"


def _check_env(var: str) -> tuple[bool, str]:
    value = os.environ.get(var, "")
    if value:
        masked = value[:3] + "***" if len(value) > 3 else "***"
        return True, f"Set ({masked})"
    return False, "Not set"


def _check_package(package: str) -> tuple[bool, str]:
    try:
        __import__(package)
        return True, "Installed"
    except ImportError:
        return False, f"Not installed - run: pip install {package}"


def _print_status(name: str, ok: bool, message: str, required: bool = False) -> None:
    icon = "[OK]" if ok else ("[!!]" if required else "[--]")
    label = name.ljust(35)
    print(f"  {icon} {label} {message}")


def _print_named_status(name: str, status: str, message: str) -> None:
    label = name.ljust(35)
    print(f"  [{status}] {label} {message}")


def _safe_check(name: str, checker, *args) -> tuple[bool, str]:
    try:
        return checker(*args)
    except Exception as exc:
        logger.debug("Readiness check failed for %s: %s", name, exc)
        return False, f"Check failed: {exc}"


def _get_available_models() -> list[str]:
    try:
        from models.model_manager import get_available_models

        return get_available_models()
    except Exception as exc:
        logger.debug("Could not list Ollama models: %s", exc)
        return []


def _select_best_model(available_models: list[str]) -> str:
    try:
        from models.model_manager import select_best_model

        return select_best_model(available_models)
    except Exception as exc:
        logger.debug("Could not select preferred model: %s", exc)
        return available_models[0] if available_models else "llama3.2:3b"


def _model_available(model_name: str, available_models: list[str]) -> bool:
    requested = str(model_name or "").replace(":", "").lower()
    if not requested:
        return False
    return any(
        requested in str(model).replace(":", "").lower()
        for model in available_models
    )


def _check_playwright() -> bool:
    try:
        from playwright.async_api import async_playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _check_chrome_harness() -> tuple[bool, str]:
    try:
        from agent.harness.launcher import (
            _CHROME_DEBUG_PORT,
            _CHROME_PROFILE,
            ensure_chrome_debug,
        )

        chrome_ready = ensure_chrome_debug()
        if chrome_ready:
            return True, f"Port {_CHROME_DEBUG_PORT} ready | Profile: {_CHROME_PROFILE}"
        return False, "Not ready (launching in background)"
    except Exception as exc:
        logger.debug("Chrome harness readiness check failed: %s", exc)
        return False, "Not ready (launching in background)"


def _check_websockets() -> tuple[str, str]:
    try:
        import websockets

        return "OK", f"v{getattr(websockets, '__version__', 'unknown')}"
    except ImportError:
        return "!!", "Not installed - run: pip install websockets"


def _check_rawvision() -> tuple[str, str]:
    rawvision_status = "--"
    rawvision_detail = "Not initialized"
    try:
        from rawvision import RawVision

        ctx = RawVision.capture()
        if len(ctx.elements) > 0:
            rawvision_status = "OK"
            layers = ",".join(getattr(layer, "value", str(layer)) for layer in ctx.layers_used)
            rawvision_detail = (
                f"{len(ctx.elements)} elements | "
                f"layers: {layers} | "
                f"{ctx.capture_ms:.0f}ms"
            )
        else:
            rawvision_status = "--"
            rawvision_detail = "No elements captured"
    except ImportError:
        rawvision_status = "--"
        rawvision_detail = "rawvision package not found"
    except Exception as exc:
        rawvision_status = "WARN"
        rawvision_detail = str(exc)[:60]
    return rawvision_status, rawvision_detail


def _check_hands() -> tuple[str, str]:
    hands_status = "--"
    hands_detail = "Not initialized"
    try:
        from agent.hands.controller import get_hands
        from agent.hands.engines.terminal_engine import TerminalEngine

        _hands = get_hands()
        _ = _hands
        term = TerminalEngine()
        ok, _out = term.run("echo hands_ok", timeout=5)
        if ok:
            hands_status = "OK"
            hands_detail = "Terminal engine ready"
        else:
            hands_status = "WARN"
            hands_detail = "Terminal engine failed"
    except Exception as exc:
        hands_status = "WARN"
        hands_detail = str(exc)[:60]
    return hands_status, hands_detail


def run_readiness_check(memory=None) -> dict:
    """
    Run all readiness checks and print a formatted summary.
    Returns dict of check results.
    Never raises - all checks are wrapped in try/except.
    """
    results = {}

    try:
        print("\n" + "=" * 58)
        print("  JARVIS STARTUP READINESS")
        print("=" * 58)

        print("\n[CORE]")
        ollama_models = _get_available_models()
        ollama_ok, ollama_msg = _safe_check("ollama", _check_ollama)
        results["ollama"] = ollama_ok
        if ollama_ok:
            print(f"  [OK] Ollama                    Running - {len(ollama_models)} model(s) available")
        else:
            print(f"  [!!] Ollama                    {ollama_msg}")

        active_model = _select_best_model(ollama_models)
        main_model_ok = bool(ollama_models) and _model_available(active_model, ollama_models)
        results["main_model"] = main_model_ok
        main_status = "OK" if main_model_ok else "!!"
        main_detail = (
            active_model
            if main_model_ok
            else f"{active_model} (not pulled yet - run: ollama pull {active_model})"
        )
        print(f"  [{main_status}] Main model (reasoning)    {main_detail}")

        action_model = os.getenv("JARVIS_ACTION_MODEL", "gemma3:4b")
        action_available = _model_available(action_model, ollama_models)
        results["action_model"] = action_available
        action_status = "OK" if action_available else "--"
        action_detail = (
            action_model
            if action_available
            else f"{action_model} (not pulled yet - run: ollama pull {action_model})"
        )
        print(f"  [{action_status}] Action model (automation) {action_detail}")

        embed_model = os.getenv("JARVIS_EMBED_MODEL", "nomic-embed-text")
        embed_available = _model_available(embed_model, ollama_models)
        results["semantic_memory"] = embed_available
        embed_status = "OK" if embed_available else "--"
        print(f"  [{embed_status}] Embed model (memory)      {embed_model}")

        if ollama_models:
            print(f"  [INFO] Available:              {', '.join(ollama_models[:5])}")
        else:
            print("  [INFO] Available:              none")

        playwright_status = "OK" if _check_playwright() else "--"
        playwright_detail = "Available" if playwright_status == "OK" else "Not installed"
        results["playwright"] = playwright_status == "OK"
        print(f"  [{playwright_status}] Playwright (browser)      {playwright_detail}")

        chrome_ready, chrome_detail = _check_chrome_harness()
        chrome_status = "OK" if chrome_ready else "--"
        results["chrome_harness"] = chrome_ready
        print(f"  [{chrome_status}] Chrome harness            {chrome_detail}")

        print("\n[MEMORY]")
        if memory is not None:
            try:
                sem_live = memory.is_semantic_available()
                _print_status(
                    "Embedding index live",
                    sem_live,
                    "Active" if sem_live else "Inactive (model not available)",
                )
            except Exception as exc:
                logger.debug("Embedding index readiness check skipped: %s", exc)

        print("\n[REMOTE BRIDGE]")
        remote_enabled = os.environ.get("JARVIS_REMOTE_BRIDGE", "false").lower() == "true"
        results["remote_bridge"] = remote_enabled
        _print_status(
            "Remote bridge",
            remote_enabled,
            "Enabled" if remote_enabled else "Disabled (set JARVIS_REMOTE_BRIDGE=true)",
        )

        ws_status, ws_detail = _check_websockets()
        results["websockets"] = ws_status == "OK"
        print(f"  [{ws_status}] WebSocket (websockets)          {ws_detail}")

        if remote_enabled:
            token_ok, token_msg = _safe_check("bridge_token", _check_env, "JARVIS_BRIDGE_TOKEN")
            results["bridge_token"] = token_ok
            _print_status("JARVIS_BRIDGE_TOKEN", token_ok, token_msg, required=True)

            telegram_ok, telegram_msg = _safe_check("telegram", _check_env, "TELEGRAM_BOT_TOKEN")
            results["telegram"] = telegram_ok
            _print_status("TELEGRAM_BOT_TOKEN", telegram_ok, telegram_msg)

        print("\n[OPTIONAL SKILLS]")
        psutil_ok, psutil_msg = _safe_check("psutil", _check_package, "psutil")
        results["psutil"] = psutil_ok
        _print_status("psutil (system monitor)", psutil_ok, psutil_msg)

        pdfplumber_ok, pdfplumber_msg = _safe_check("pdfplumber", _check_package, "pdfplumber")
        results["pdfplumber"] = pdfplumber_ok
        _print_status("pdfplumber (PDF reading)", pdfplumber_ok, pdfplumber_msg)

        smtp_ok, smtp_msg = _safe_check("smtp", _check_env, "JARVIS_SMTP_HOST")
        results["smtp"] = smtp_ok
        _print_status("SMTP (send_email skill)", smtp_ok, smtp_msg)

        print("\n[VISION]")
        vision_model = os.environ.get("JARVIS_VISION_MODEL", "llava")
        vision_ok, vision_msg = _safe_check("vision", _check_model, vision_model)
        results["vision"] = vision_ok
        _print_status(f"Vision model ({vision_model})", vision_ok, vision_msg)

        mss_ok, mss_msg = _safe_check("mss", _check_package, "mss")
        results["mss"] = mss_ok
        _print_status("mss (screen capture)", mss_ok, mss_msg)

        vision_verify = os.environ.get("JARVIS_VISION_VERIFY", "false").lower() == "true"
        results["vision_verify"] = vision_verify
        if vision_verify:
            _print_status("Screenshot verification", True, "Enabled")
        else:
            _print_status(
                "Screenshot verification",
                False,
                "Disabled - to enable, run BEFORE starting Jarvis:\n"
                "             PowerShell: $env:JARVIS_VISION_VERIFY = \"true\"\n"
                "             CMD:        set JARVIS_VISION_VERIFY=true",
            )

        rawvision_status, rawvision_detail = _check_rawvision()
        results["rawvision"] = rawvision_status == "OK"
        _print_named_status("RawVision", rawvision_status, rawvision_detail)

        hands_status, hands_detail = _check_hands()
        results["hands"] = hands_status == "OK"
        _print_named_status("Jarvis Hands", hands_status, hands_detail)

        print("\n" + "=" * 58)
        critical = [key for key in ("ollama", "main_model") if not results.get(key)]

        if critical:
            print(f"  [!!] {len(critical)} critical issue(s) - Jarvis may not work correctly")
            for key in critical:
                print(f"     Fix: see [{key.upper()}] section above")
        else:
            optional_missing = sum(1 for value in results.values() if not value)
            print("  [OK] Core systems ready")
            if optional_missing:
                print(f"  [--] {optional_missing} optional feature(s) not configured")

        print("=" * 58 + "\n")
    except Exception as exc:
        logger.debug("Readiness check error (non-critical): %s", exc)

    return results
