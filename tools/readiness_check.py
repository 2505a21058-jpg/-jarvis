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


def _safe_check(name: str, checker, *args) -> tuple[bool, str]:
    try:
        return checker(*args)
    except Exception as exc:
        logger.debug("Readiness check failed for %s: %s", name, exc)
        return False, f"Check failed: {exc}"


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
        ollama_ok, ollama_msg = _safe_check("ollama", _check_ollama)
        results["ollama"] = ollama_ok
        _print_status("Ollama", ollama_ok, ollama_msg, required=True)

        available = []
        try:
            from models.model_manager import get_available_models, get_best_available_model

            active_model = os.environ.get("JARVIS_MODEL", "") or get_best_available_model()
            available = get_available_models()
            if available:
                model_ok = True
                model_msg = f"Using: {active_model}"
                results["main_model"] = True
            else:
                model_ok = False
                model_msg = "No models found - run: ollama pull llama3.2:3b"
                results["main_model"] = False
        except Exception as exc:
            # Model auto-detection failures are logged without blocking readiness output.
            logger.debug("Model readiness auto-detection failed: %s", exc)
            model_ok = False
            model_msg = "Could not detect model"
            results["main_model"] = False

        _print_status("Language model", model_ok, model_msg, required=True)

        if ollama_ok and available:
            print(f"  [INFO] Available: {', '.join(available[:5])}")

        print("\n[MEMORY]")
        embed_ok, embed_msg = _safe_check("semantic_memory", _check_model, "nomic-embed-text")
        results["semantic_memory"] = embed_ok
        _print_status("Semantic memory (nomic-embed-text)", embed_ok, embed_msg)

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
