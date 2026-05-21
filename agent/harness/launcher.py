"""
agent/harness/launcher.py

Ensures Chrome is always running with --remote-debugging-port=9222.
Always uses the dedicated Jarvis Chrome profile (Profile 3).
Never touches user's personal Chrome profiles.

Key behaviors:
- Pre-launch at Jarvis startup (not on-demand)
- Single launch guard prevents concurrent launches
- 35 second wait for Chrome to be ready
- Always uses Profile 3 (jarvis profile)
- Graceful fallback if Chrome unavailable
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import urllib.request
from typing import Optional

logger = logging.getLogger("jarvis.harness.launcher")

# Configuration

_CHROME_EXE = os.getenv(
    "JARVIS_CHROME_EXE",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)

_CHROME_USER_DATA = os.getenv(
    "JARVIS_CHROME_USER_DATA",
    r"C:\Users\shiva\AppData\Local\Google\Chrome\User Data"
)

_CHROME_FALLBACK_USER_DATA = os.getenv(
    "JARVIS_CHROME_FALLBACK_USER_DATA",
    os.path.join(
        os.getenv("LOCALAPPDATA", os.path.expanduser("~")),
        "Jarvis",
        "ChromeDebugUserData",
    ),
)

_CHROME_PROFILE = os.getenv(
    "JARVIS_CHROME_PROFILE",
    "Profile 3"   # jarvis profile
)

_CHROME_DEBUG_PORT = int(
    os.getenv("JARVIS_CHROME_DEBUG_PORT", "9222")
)

_LAUNCH_TIMEOUT = float(
    os.getenv("JARVIS_CHROME_LAUNCH_TIMEOUT", "35")
)

# Launch guard - prevents concurrent launches

_launch_lock = threading.Lock()
_launch_in_progress = False
_launch_succeeded = False
_launch_attempted = False


# Public API

def is_chrome_debug_available(
    port: int = _CHROME_DEBUG_PORT
) -> bool:
    """Check if Chrome debug port is responding."""
    try:
        url = f"http://localhost:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_chrome_tabs(
    port: int = _CHROME_DEBUG_PORT
) -> list[dict]:
    """Get open tabs from Chrome debug port."""
    try:
        url = f"http://localhost:{port}/json"
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


def get_chrome_version(
    port: int = _CHROME_DEBUG_PORT
) -> str:
    """Get Chrome version string."""
    try:
        url = f"http://localhost:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
            return data.get("Browser", "unknown")
    except Exception:
        return "unknown"


def ensure_chrome_debug(
    port: int = _CHROME_DEBUG_PORT
) -> bool:
    """
    Ensure Chrome is running with debug port and jarvis profile.
    Safe to call multiple times - uses launch guard.
    Called at Jarvis startup.
    Returns True if Chrome debug port is available.
    """
    global _launch_in_progress, _launch_succeeded, _launch_attempted

    # Already available
    if is_chrome_debug_available(port):
        version = get_chrome_version(port)
        logger.info(
            "[LAUNCHER] Chrome debug port %s available (%s) "
            "profile=%s",
            port, version, _CHROME_PROFILE
        )
        return True

    # Another thread is launching - wait for it
    if _launch_in_progress:
        logger.info(
            "[LAUNCHER] Chrome launch already in progress, "
            "waiting..."
        )
        for _ in range(max(1, int(_LAUNCH_TIMEOUT / 0.5))):
            time.sleep(0.5)
            if is_chrome_debug_available(port):
                return True
        return False

    # Acquire launch lock
    with _launch_lock:
        # Double-check after acquiring lock
        if is_chrome_debug_available(port):
            return True

        if _launch_attempted:
            logger.info(
                "[LAUNCHER] Chrome launch already attempted; "
                "not starting another Chrome process"
            )
            return False

        _launch_attempted = True
        _launch_in_progress = True
        try:
            result = _launch_chrome(port)
            _launch_succeeded = result
            return result
        finally:
            _launch_in_progress = False


def find_electron_port(app_name: str) -> Optional[int]:
    """Find CDP debug port for Electron app."""
    _ELECTRON_PORTS = {
        "vscode":   [9229, 9230],
        "discord":  [13172, 13173],
        "spotify":  [4370, 4371],
        "slack":    [9222, 9223],
        "notion":   [9222, 9223],
    }
    app_lower = app_name.lower()
    for known, ports in _ELECTRON_PORTS.items():
        if known in app_lower:
            for port in ports:
                if is_chrome_debug_available(port):
                    logger.info(
                        "[LAUNCHER] Found %s CDP on port %s",
                        app_name, port
                    )
                    return port
    return None


# Internal

def _build_chrome_args(port: int, user_data_dir: str) -> list[str]:
    return [
        _CHROME_EXE,
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={user_data_dir}",
        f"--profile-directory={_CHROME_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-extensions-except=",
        "--disable-default-apps",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]


def _start_chrome(args: list[str]) -> bool:
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        return True
    except Exception as e:
        logger.error("[LAUNCHER] Chrome launch failed: %s", e)
        return False


def _launch_chrome_fallback(port: int) -> bool:
    """Try launching Chrome with isolated user-data-dir (always works)."""
    fallback_user_data = os.path.abspath(_CHROME_FALLBACK_USER_DATA)
    try:
        os.makedirs(fallback_user_data, exist_ok=True)
    except Exception as exc:
        logger.warning(
            "[LAUNCHER] Could not prepare fallback Chrome profile: %s",
            exc,
        )
    logger.info(
        "[LAUNCHER] Using isolated user-data-dir=%s",
        fallback_user_data,
    )
    fallback_args = _build_chrome_args(port, fallback_user_data)
    if _start_chrome(fallback_args) and _wait_for_debug_port(
        port,
        _LAUNCH_TIMEOUT,
    ):
        return True
    logger.warning(
        "[LAUNCHER] Chrome launched but port %s not ready "
        "after %.0fs. Browser skills may fail.",
        port, _LAUNCH_TIMEOUT
    )
    return False


def _wait_for_debug_port(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    check_interval = 0.5
    while time.time() < deadline:
        if is_chrome_debug_available(port):
            elapsed = timeout - (deadline - time.time())
            logger.info(
                "[LAUNCHER] Chrome ready in %.1fs | profile=%s",
                elapsed, _CHROME_PROFILE
            )
            return True
        time.sleep(check_interval)
    return False


def _launch_chrome(port: int) -> bool:
    """
    Launch Chrome with debug port and jarvis profile.
    Waits up to _LAUNCH_TIMEOUT seconds for port to be ready.
    """
    if not os.path.exists(_CHROME_EXE):
        logger.error(
            "[LAUNCHER] Chrome not found at: %s", _CHROME_EXE
        )
        return False

    # Check if the requested profile actually exists
    profile_dir = os.path.join(os.path.abspath(_CHROME_USER_DATA), _CHROME_PROFILE)
    if not os.path.isdir(profile_dir):
        logger.info(
            "[LAUNCHER] Profile '%s' not found at %s; "
            "using isolated user-data-dir",
            _CHROME_PROFILE, profile_dir
        )
        return _launch_chrome_fallback(port)

    args = _build_chrome_args(port, _CHROME_USER_DATA)

    logger.info(
        "[LAUNCHER] Launching Chrome | profile=%s | port=%s",
        _CHROME_PROFILE, port
    )

    if not _start_chrome(args):
        return False

    if _wait_for_debug_port(port, _LAUNCH_TIMEOUT):
        return True

    return _launch_chrome_fallback(port)

    return _launch_chrome_fallback(port)
